"""Budget-aware dynamic context orchestration (v0.4 DCO).

One call decides *what enters the context window* for a task, splitting the
token budget across purpose-built buckets:

- **session**   — pointer to the latest ContextSnapshot for the session
- **bedrock**   — authority-track constants (pinned / permanent); repeated in
                  every pack on purpose, exempt from session dedup
- **warnings**  — proactive: relevant `warning` memories surface before risky
                  work even when the task wording never matches them
- **procedures**— proactive: the strongest live `procedure` memories
- **task**      — relevance-ranked recall for the task itself (inherits the
                  full retrieval stack: FTS, semantic, resonance, profiles)

With a `session_id`, repeated calls implement iterative deepening: memories
already delivered this session are excluded (except bedrock), so each call
digs further instead of repeating itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .context_pack import approx_tokens
from .schema import MemoryRecord

DEFAULT_BUDGET_SPLIT = {
    "session": 0.08,
    "bedrock": 0.20,
    "warnings": 0.14,
    "procedures": 0.12,
    "task": 0.46,
}

# Task-type detection: lightweight, deterministic emphasis shifts. Risky verbs
# grow the warnings bucket; how-to intent grows procedures; both shifts come
# out of the task bucket so the total split stays 1.0.
RISK_TERMS = {
    "delete", "drop", "purge", "wipe", "truncate", "overwrite", "force",
    "deploy", "migrate", "migration", "rollback", "restart", "shutdown",
    "destroy", "remove", "reset", "revoke",
}
HOWTO_TERMS = {
    "how", "procedure", "steps", "setup", "install", "configure",
    "configuration", "guide", "walkthrough", "run", "execute", "perform",
}
EMPHASIS_SHIFT = 0.08


def detect_emphasis(task: str) -> list[str]:
    words = {word.lower() for word in task.replace("/", " ").split()}
    emphasis = []
    if words & RISK_TERMS:
        emphasis.append("risk")
    if words & HOWTO_TERMS:
        emphasis.append("howto")
    return emphasis


def budget_split_for(task: str) -> tuple[dict[str, float], list[str]]:
    split = dict(DEFAULT_BUDGET_SPLIT)
    emphasis = detect_emphasis(task)
    if "risk" in emphasis:
        split["warnings"] += EMPHASIS_SHIFT
        split["task"] -= EMPHASIS_SHIFT
    if "howto" in emphasis:
        split["procedures"] += EMPHASIS_SHIFT
        split["task"] -= EMPHASIS_SHIFT
    return split, emphasis
SECTION_ORDER = ["session", "bedrock", "warnings", "procedures", "task"]
SECTION_HEADERS = {
    "session": "## SESSION STATE",
    "bedrock": "## BEDROCK (always-on constants)",
    "warnings": "## WARNINGS (heed before acting)",
    "procedures": "## PROCEDURES",
    "task": "## RELEVANT MEMORY",
}
PROACTIVE_MIN = 2


@dataclass
class OrchestratedContext:
    text: str
    sections: dict[str, dict] = field(default_factory=dict)
    used_tokens: int = 0
    max_tokens: int = 0
    session_id: str | None = None
    delivered_ids: list[str] = field(default_factory=list)
    emphasis: list[str] = field(default_factory=list)


def _line(record: MemoryRecord) -> str:
    pin = " [PINNED]" if record.pinned else ""
    return f"- ({record.scope}/{record.type}{pin}) {record.content}"


def orchestrate_context(
    client,
    task: str,
    *,
    session_id: str | None = None,
    requester_agent_id: str | None = None,
    requester_team_id: str | None = None,
    max_tokens: int = 2000,
    profile=None,
) -> OrchestratedContext:
    if max_tokens < 128:
        raise ValueError("max_tokens must be >= 128")
    store = client.store
    seen = store.delivered_ids(session_id) if session_id else set()

    task_results = client.search(
        task,
        requester_agent_id=requester_agent_id,
        requester_team_id=requester_team_id,
        limit=24,
        profile=profile,
    )
    bedrock = store.bedrock_records(
        requester_agent_id=requester_agent_id,
        requester_team_id=requester_team_id,
        limit=6,
    )
    placed: set[str] = {record.id for record in bedrock}

    def take_type(memory_type: str) -> list[MemoryRecord]:
        picked = [
            result.record
            for result in task_results
            if result.record.type == memory_type
            and result.record.id not in placed
            and result.record.id not in seen
        ]
        if len(picked) < PROACTIVE_MIN:
            for record in store.top_records_by_type(
                memory_type,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                limit=PROACTIVE_MIN * 2,
            ):
                if record.id not in placed and record.id not in seen and all(
                    record.id != existing.id for existing in picked
                ):
                    picked.append(record)
                if len(picked) >= PROACTIVE_MIN:
                    break
        for record in picked:
            placed.add(record.id)
        return picked

    buckets: dict[str, list[str]] = {name: [] for name in SECTION_ORDER}
    # The task bucket is built AFTER warnings/procedures actually emit: a record
    # claimed by take_type but dropped by its section's token cap must still be
    # eligible for the task section (which has the largest share + surplus),
    # rather than vanishing from the pack entirely.
    bucket_records: dict[str, list] = {
        "bedrock": bedrock,
        "warnings": take_type("warning"),
        "procedures": take_type("procedure"),
    }

    session_lines: list[str] = []
    if session_id:
        snapshot = store.latest_snapshot_record(session_id)
        if snapshot is not None:
            session_lines.append(
                f"- Context snapshot {snapshot.id} available for session "
                f"{session_id} (saved {snapshot.created_at}); reload it with "
                f"memory_reload_context before resuming interrupted work."
            )

    split, emphasis = budget_split_for(task)
    caps = {name: int(max_tokens * share) for name, share in split.items()}
    sections: dict[str, dict] = {}
    lines: list[str] = []
    used_total = 0
    surplus = 0

    def emit(name: str, entry_lines: list[str], ids: list[str], cap: int) -> None:
        nonlocal used_total, surplus
        if not entry_lines:
            surplus += cap
            return
        header = SECTION_HEADERS[name]
        used = approx_tokens(header) + 1
        kept_lines: list[str] = []
        kept_ids: list[str] = []
        for entry, memory_id in zip(entry_lines, ids):
            cost = approx_tokens(entry) + 1
            if used + cost > cap:
                continue
            used += cost
            kept_lines.append(entry)
            kept_ids.append(memory_id)
        if not kept_lines:
            surplus += cap
            return
        lines.append(header)
        lines.extend(kept_lines)
        lines.append("")
        used_total += used
        surplus += cap - used
        sections[name] = {"memory_ids": [i for i in kept_ids if i], "used_tokens": used}

    emit("session", session_lines, [""] * len(session_lines), caps["session"])
    for name in ("bedrock", "warnings", "procedures"):
        records = bucket_records[name]
        emit(name, [_line(record) for record in records], [record.id for record in records], caps[name])

    # Only records that were ACTUALLY emitted above are excluded from task —
    # anything a higher section claimed but couldn't fit falls through here.
    emitted_ids = {record.id for record in bedrock}
    for name in ("warnings", "procedures"):
        emitted_ids.update(sections.get(name, {}).get("memory_ids", []))
    task_records = [
        result.record
        for result in task_results
        if result.record.id not in emitted_ids and result.record.id not in seen
    ]
    emit(
        "task",
        [_line(record) for record in task_records],
        [record.id for record in task_records],
        caps["task"] + surplus,  # unused budget flows to task recall
    )

    delivered = [
        memory_id
        for name in ("warnings", "procedures", "task")
        for memory_id in sections.get(name, {}).get("memory_ids", [])
    ]
    if session_id and delivered:
        store.record_delivery(session_id, delivered)

    return OrchestratedContext(
        text="\n".join(lines).rstrip() + ("\n" if lines else ""),
        sections=sections,
        used_tokens=used_total,
        max_tokens=max_tokens,
        session_id=session_id,
        delivered_ids=delivered,
        emphasis=emphasis,
    )
