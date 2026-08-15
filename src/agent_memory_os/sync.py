"""Federated sync: portable JSONL bundles + peer transport.

`export_bundle` writes memories, links, recall profiles, and tombstones as one
JSONL file; `import_bundle` merges a bundle into another store with
deterministic, convergent conflict resolution:

- memories: last-writer-wins on canonical-stamp `updated_at`, with a content
  tie-break so two nodes that edited in the same second still converge
- links: merged keeping the strongest weight, highest activation count, and
  latest activation timestamp
- profiles: last-writer-wins on `updated_at`
- tombstones: a deletion propagates and blocks the row from resurrecting

What leaves for a given peer is decided by that peer's **policy** (see
`MemoryStore.add_peer`): 'full' (whole store, own trusted nodes only), 'shared'
(everything except private `visibility=[]` memories), or 'team:<id>' (one
project). Private memories never leave under 'shared'/'team'. On import, a
non-'full' (semi-trusted) peer may not inject globally-visible memories, and
every imported row records `source.synced_from`.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Set as AbstractSet
from contextlib import contextmanager, nullcontext
from pathlib import Path

from .constants import (
    SYNC_BUNDLE_VERSION,
    SYNC_HTTP_TIMEOUT_SECONDS,
    SYNC_MAX_FUTURE_SKEW_SECONDS,
)
from .sync_bundles.codec import decode_header, decode_record
from .timestamp_converters import (
    stamp_distance_to_now_seconds,
    stamp_distance_to_stamp_seconds,
    stamp_to_dt,
)


def _guard(lock):
    """Hold `lock` around a DB operation, or nothing when called single-threaded.

    Peer HTTP round-trips must run OUTSIDE this so a slow/unreachable peer never
    freezes every other request on a shared server connection.
    """
    return lock if lock is not None else nullcontext()

BUNDLE_VERSION = SYNC_BUNDLE_VERSION
_MEMORY_KEYS = (
    "id", "owner", "scope", "type", "content", "summary", "tags", "visibility",
    "source", "confidence", "importance", "created_at", "updated_at", "acl_updated_at",
    "expires_at", "decay_policy", "decay_half_life_days", "last_accessed_at",
    "access_count", "pinned", "helpful_count", "unhelpful_count",
)
# Keys that carry the memory's ACL, merged on the independent acl_updated_at
# clock rather than the content updated_at clock.
_ACL_KEYS = ("visibility", "acl_updated_at")
_LINK_KEYS = (
    "src_id", "dst_id", "relation", "weight", "created_at", "updated_at",
    "last_activated_at", "activation_count", "source",
)


@contextmanager
def _atomic_bundle_writer(path: Path):
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".jsonl",
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            yield handle
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _incoming_wins(
    incoming_stamp: str,
    incoming_content: str,
    existing_stamp: str,
    existing_content: str,
) -> bool:
    """LWW with a deterministic tie-break, so both nodes converge identically."""
    distance = stamp_distance_to_stamp_seconds(incoming_stamp, existing_stamp)
    if distance != 0:
        return distance > 0
    return incoming_content > existing_content


# A forged far-future stamp would win an LWW clock indefinitely and could not
# be corrected by a legitimate later update. Reject protected clocks beyond
# now plus the allowed transport skew.
def _stamp_too_future(stamp: str) -> bool:
    """Return whether an incoming protected clock exceeds the future-skew limit."""
    return (
        stamp_distance_to_now_seconds(stamp)
        > SYNC_MAX_FUTURE_SKEW_SECONDS
    )


def _org_member_wins(inc_members, ex_members) -> bool:
    """Deterministic tie-break for equal-timestamp org member sets: the
    lexicographically-greater sorted set wins, so both nodes converge to the
    same membership instead of each keeping its own (a divergence bug)."""
    return sorted(str(m) for m in (inc_members or [])) > sorted(
        str(m) for m in (ex_members or [])
    )


def _org_scope_allows(org_scope: str | None, kind: str, id_: str,
                      *, team_of: str | None,
                      project_parent: tuple[str, frozenset[str]] | None = None,
                      asserted_members=None) -> bool:
    """Whether a peer authorized for `org_scope` may assert an org record.

    org_scope is the pulling peer's policy: None (no org mutations permitted,
    e.g. an anonymous push or a 'shared' peer), 'full' (own trusted replica —
    anything), 'team:<id>' (only that team and projects under it), or
    'project:<id>' (only that one project). `team_of` is the project's parent
    team id when known (from the record or a local lookup), used to authorize a
    team-scoped peer's project mutations.
    """
    if not org_scope:
        return False
    if org_scope == "full":
        return True
    if org_scope.startswith("team:"):
        t = org_scope[len("team:"):]
        if kind == "team":
            return id_ == t
        if kind == "project":
            return team_of == t
        return False
    if org_scope.startswith("project:"):
        p = org_scope[len("project:"):]
        if kind == "project":
            return id_ == p
        if kind == "team" and project_parent is not None:
            parent_id, project_members = project_parent
            return (
                id_ == parent_id
                and frozenset(_clean_members(asserted_members)) == project_members
            )
        return False
    return False


def export_bundle(
    store,
    path: str | Path,
    *,
    since: str | None = None,
    team: str | None = None,
    project: str | None = None,
    include_private: bool = True,
    include_org: bool = True,
    node_name: str = "",
) -> dict[str, int]:
    """Write a bundle.

    `team` restricts exported memories to one team's shared memory; `project`
    restricts them to one project's shared memory. `include_private` controls
    whether memories with `visibility=[]` are exported.

    Memory tombstones are not filtered by `team`, `project`, or
    `include_private`; when `since` is supplied, only tombstones later than
    that cursor are included. Each carries a memory id and deletion stamp, but
    no memory content.

    Organization tombstones are exported only when `include_org` is true.
    They are filtered by `since`, but not by the selected team or project
    scope.
    """
    since_cursor = since
    if since_cursor is not None:
        stamp_to_dt(since_cursor)
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"memories": 0, "links": 0, "profiles": 0, "tombstones": 0}
    clauses, params = [], []
    eligibility_clauses, eligibility_params = [], []
    if since_cursor:
        # A pure ACL change (share/revoke) bumps acl_updated_at, not updated_at,
        # so an incremental export must ship it too.
        clauses.append("(updated_at > ? OR acl_updated_at > ?)")
        params.extend([since_cursor, since_cursor])
    if team:
        team_clause = (
            "(EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = ?)"
            " OR EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = 'team'"
            "            AND json_extract(source, '$.team_id') = ?))"
        )
        clauses.append(team_clause)
        params.extend([f"team:{team}", team])
        eligibility_clauses.append(team_clause)
        eligibility_params.extend([f"team:{team}", team])
    if project:
        project_clause = "EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = ?)"
        clauses.append(project_clause)
        params.append(f"project:{project}")
        eligibility_clauses.append(project_clause)
        eligibility_params.append(f"project:{project}")
    if not include_private:
        # Private == empty visibility array. Keep only rows granted to someone.
        private_clause = "json_array_length(visibility) > 0"
        clauses.append(private_clause)
        eligibility_clauses.append(private_clause)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _atomic_bundle_writer(path) as handle:
        header = {"kind": "bundle", "version": BUNDLE_VERSION}
        if node_name:
            header["node_name"] = node_name
        contract, header = decode_header(header)
        handle.write(json.dumps(header, ensure_ascii=False) + "\n")

        def _write_record(record: dict) -> None:
            decoded = decode_record(contract, record)
            if decoded is None:
                raise ValueError("current bundle contract rejected a record kind")
            handle.write(json.dumps(decoded.entry, ensure_ascii=False) + "\n")

        for row in store.conn.execute(f"SELECT * FROM memories {where}", params):
            payload = {key: row[key] for key in _MEMORY_KEYS}
            _write_record({"kind": "memory", **payload})
            counts["memories"] += 1
        link_where, link_params = (
            ("WHERE updated_at > ?", [since_cursor]) if since_cursor else ("", [])
        )
        for row in store.conn.execute(f"SELECT * FROM memory_links {link_where}", link_params):
            # Both endpoints must still be eligible for this scope/privacy
            # boundary, even when an incremental bundle omits unchanged rows.
            # Query only this fresh link's endpoints instead of materializing
            # every scope-eligible memory id in Python.
            endpoint_ids = sorted({row["src_id"], row["dst_id"]})
            placeholders = ", ".join("?" for _ in endpoint_ids)
            endpoint_clauses = [f"id IN ({placeholders})", *eligibility_clauses]
            eligible_endpoint_count = store.conn.execute(
                f"SELECT COUNT(*) FROM memories WHERE {' AND '.join(endpoint_clauses)}",
                [*endpoint_ids, *eligibility_params],
            ).fetchone()[0]
            if eligible_endpoint_count != len(endpoint_ids):
                continue
            payload = {key: row[key] for key in _LINK_KEYS}
            _write_record({"kind": "link", **payload})
            counts["links"] += 1
        members = None
        scope_membership_fresh = False
        if project:
            proj = store.get_project(project)
            members = set(proj["members"]) if proj else set()
            scope_membership_fresh = bool(
                since_cursor is not None
                and proj
                and stamp_distance_to_stamp_seconds(
                    proj["updated_at"],
                    since_cursor,
                ) > 0
            )
        elif team:
            members = {
                agent["id"] for agent in store.list_agents() if team in agent["teams"]
            }
            selected_team = store.get_team(team)
            scope_membership_fresh = bool(
                since_cursor is not None
                and selected_team
                and stamp_distance_to_stamp_seconds(
                    selected_team["updated_at"],
                    since_cursor,
                ) > 0
            )
        profile_where, profile_params = (
            ("WHERE updated_at > ?", [since_cursor])
            if since_cursor is not None and not scope_membership_fresh
            else ("", [])
        )
        for row in store.conn.execute(
            f"SELECT * FROM recall_profiles {profile_where}",
            profile_params,
        ):
            if members is not None and row["agent_id"] not in members:
                continue
            _write_record({"kind": "profile", **dict(row)})
            counts["profiles"] += 1
        for mem_id, deleted_at in store.list_tombstones(since=since_cursor):
            _write_record(
                {"kind": "tombstone", "id": mem_id, "deleted_at": deleted_at}
            )
            counts["tombstones"] += 1
        # Org structure (federate teams/projects/memberships so ACL definitions
        # converge across nodes). Only emitted when include_org — a memory-only
        # 'shared' peer must not learn the node's whole membership graph. Scoped
        # to match the memory scope; teams are written before projects so the
        # import can honour the subset invariant.
        if include_org:
            if project:
                proj = store.get_project(project)
                parent = store.get_team(proj["team_id"]) if proj else None
                # A project-scoped peer may only learn the project's own members.
                # Emit the parent team with its roster narrowed to those members
                # so the subset invariant holds on the peer WITHOUT leaking the
                # ids of team members outside this project.
                if parent:
                    parent = {**parent, "members": [
                        m for m in parent["members"] if m in set(proj["members"])
                    ]}
                team_rows = [parent] if parent else []
                project_rows = [proj] if proj else []
            elif team:
                t = store.get_team(team)
                team_rows = [t] if t else []
                project_rows = store.list_projects(team)
            else:
                team_rows = store.list_teams()
                project_rows = store.list_projects()

            def _fresh(row):  # respect the incremental `since` cursor like memories do
                if since_cursor is None:
                    return True
                return (
                    stamp_distance_to_stamp_seconds(
                        row["updated_at"],
                        since_cursor,
                    )
                    > 0
                )

            for t in team_rows:
                if not _fresh(t):
                    continue
                _write_record({
                    "kind": "team", "id": t["id"], "name": t["name"],
                    "updated_at": t["updated_at"], "members": t["members"],
                })
            for pr in project_rows:
                if not _fresh(pr):
                    continue
                _write_record({
                    "kind": "project", "id": pr["id"], "team_id": pr["team_id"], "name": pr["name"],
                    "updated_at": pr["updated_at"], "members": pr["members"],
                })
            for tkind, tid, deleted_at in store.list_org_tombstones(since=since_cursor):
                _write_record({
                    "kind": "org_tombstone", "tomb_kind": tkind, "id": tid, "deleted_at": deleted_at,
                })
    return counts


def import_bundle(
    store,
    path: str | Path,
    *,
    source_peer: str | None = None,
    trusted: bool = True,
    org_scope: str | None = "full",
) -> dict[str, int]:
    """Merge a bundle into the store.

    `trusted=False` (a semi-trusted 'shared'/'team' peer) forbids injecting
    NEW globally-visible memories and records `source.synced_from`.

    `org_scope` authorizes org-structure (team/project/membership) mutations —
    these DEFINE ACLs, so an untrusted peer must not rewrite arbitrary ones.
    'full' (a local/admin import or own replica): any org record. 'team:<id>' /
    'project:<id>': only that scope. None: no org mutations at all (an anonymous
    network push, or a memory-only 'shared' peer). The whole merge is atomic: a
    corrupt line rolls everything back.
    """
    path = Path(path).expanduser()
    stats = {
        "memories_added": 0, "memories_updated": 0, "memories_skipped": 0,
        "links_added": 0, "links_merged": 0, "profiles_upserted": 0,
        "tombstones_applied": 0, "teams_upserted": 0, "projects_upserted": 0,
        "org_tombstones_applied": 0, "org_records_rejected": 0,
    }
    # A semi-trusted peer must not forge a memory authored by one of OUR local
    # agents (impersonation). Compute the guarded id set once.
    local_agents: AbstractSet[str] = (
        set() if trusted else {a["id"] for a in store.list_agents()}
    )
    try:
        with path.open("r", encoding="utf-8") as handle:
            header = json.loads(handle.readline())
            contract, _ = decode_header(header)
            project_parent = None
            if org_scope and org_scope.startswith("project:"):
                # The parent team is written before its project, so validate
                # the one project record first without buffering the bundle.
                project_id = org_scope[len("project:"):]
                project_entry = None
                project_count = 0
                project_tombstone = None
                for line in handle:
                    decoded = decode_record(contract, json.loads(line))
                    if decoded is None:
                        continue
                    candidate = decoded.entry
                    if candidate["kind"] == "project" and candidate["id"] == project_id:
                        project_count += 1
                        project_entry = candidate if project_count == 1 else None
                    elif (
                        candidate["kind"] == "org_tombstone"
                        and candidate["tomb_kind"] == "project"
                        and candidate["id"] == project_id
                        and not _stamp_too_future(candidate["deleted_at"])
                        and (
                            project_tombstone is None
                            or stamp_distance_to_stamp_seconds(
                                candidate["deleted_at"],
                                project_tombstone,
                            ) > 0
                        )
                    ):
                        project_tombstone = candidate["deleted_at"]
                local_project = store.get_project(project_id)
                if project_entry is not None:
                    parent_id = (
                        local_project["team_id"]
                        if local_project is not None
                        else project_entry.get("team_id") or ""
                    )
                    if (
                        parent_id
                        and not _stamp_too_future(project_entry["updated_at"])
                        and _project_version_would_merge(store, project_entry)
                        and not (
                            project_tombstone is not None
                            and stamp_distance_to_stamp_seconds(
                                project_tombstone,
                                project_entry["updated_at"],
                            ) >= 0
                        )
                    ):
                        project_parent = (
                            parent_id,
                            frozenset(_clean_members(project_entry.get("members"))),
                        )
                elif project_count == 0 and local_project is not None:
                    tomb = _org_tomb_at(store, "project", project_id)
                    local_version = local_project["updated_at"]
                    local_tomb_blocks = (
                        tomb is not None
                        and stamp_distance_to_stamp_seconds(tomb, local_version) >= 0
                    )
                    bundle_tomb_blocks = (
                        project_tombstone is not None
                        and stamp_distance_to_stamp_seconds(
                            project_tombstone,
                            local_version,
                        ) >= 0
                    )
                    if not local_tomb_blocks and not bundle_tomb_blocks:
                        project_parent = (
                            local_project["team_id"],
                            frozenset(_clean_members(local_project.get("members"))),
                        )
                handle.seek(0)
                header = json.loads(handle.readline())
                contract, _ = decode_header(header)

            for line in handle:
                decoded = decode_record(contract, json.loads(line))
                if decoded is None:
                    continue
                entry = dict(decoded.entry)
                kind = entry.pop("kind")
                if kind == "memory":
                    _merge_memory(
                        store, entry, stats,
                        source_peer=source_peer, trusted=trusted, local_agents=local_agents,
                    )
                elif kind == "link":
                    _merge_link(store, entry, stats)
                elif kind == "profile":
                    _merge_profile(store, entry, stats)
                elif kind == "tombstone":
                    _apply_tombstone(store, entry, stats)
                elif kind == "team":
                    _merge_team(
                        store,
                        entry,
                        stats,
                        org_scope=org_scope,
                        project_parent=project_parent,
                    )
                elif kind == "project":
                    _merge_project(store, entry, stats, org_scope=org_scope)
                elif kind == "org_tombstone":
                    _apply_org_tombstone(store, entry, stats, org_scope=org_scope)
    except Exception:
        store.conn.rollback()
        raise
    store.conn.commit()
    # Imported memberships change ACL resolution — drop the cached sets.
    if hasattr(store, "_invalidate_membership_caches"):
        store._invalidate_membership_caches()
    return stats


def _merge_memory(store, entry: dict, stats: dict, *, source_peer=None,
                  trusted=True, local_agents: AbstractSet[str] = frozenset()) -> None:
    entry = dict(entry)
    # A deletion that happened at or after this version wins over the re-add.
    tomb = store.tombstone_for(entry["id"])
    if tomb is not None and (
        stamp_distance_to_stamp_seconds(tomb, entry["updated_at"]) >= 0
    ):
        stats["memories_skipped"] += 1
        return

    existing = store.conn.execute(
        "SELECT updated_at, content, visibility, acl_updated_at FROM memories WHERE id = ?",
        (entry["id"],),
    ).fetchone()

    if not trusted:
        # Anti-impersonation: a semi-trusted peer cannot stand up a NEW memory
        # authored by one of our local agents. Genuine shared/global memory
        # under the peer's own owner ids still flows; every import records its
        # origin in source.synced_from so it is never mistaken for local.
        if existing is None and entry.get("owner") in local_agents:
            stats["memories_skipped"] += 1
            return
        entry["source"] = _tag_source(entry.get("source"), source_peer)

    inc_acl = entry["acl_updated_at"]

    if existing is None:
        if _stamp_too_future(inc_acl):
            stats["memories_skipped"] += 1
            return
        columns = ", ".join(_MEMORY_KEYS)
        placeholders = ", ".join("?" for _ in _MEMORY_KEYS)
        row = dict(entry)
        store.conn.execute(
            f"INSERT INTO memories({columns}) VALUES ({placeholders})",
            [row.get(key) for key in _MEMORY_KEYS],
        )
        stats["memories_added"] += 1
        return

    changed = False
    # (1) Content fields — merged on updated_at (never overwrite the ACL here).
    if _incoming_wins(
        entry["updated_at"], entry.get("content") or "",
        existing["updated_at"], existing["content"] or "",
    ):
        content_keys = [k for k in _MEMORY_KEYS if k not in _ACL_KEYS and k != "id"]
        assignments = ", ".join(f"{key} = ?" for key in content_keys)
        store.conn.execute(
            f"UPDATE memories SET {assignments} WHERE id = ?",
            [entry.get(key) for key in content_keys] + [entry["id"]],
        )
        changed = True
    # (2) ACL — merged on the INDEPENDENT acl_updated_at clock, so a revoke or a
    # re-share propagates even when the content is otherwise unchanged, and a
    # newer local ACL is never clobbered by an older incoming one.
    #
    # SECURITY: an untrusted peer must not use this path to ESCALATE visibility
    # (e.g. re-classify a `team:X` memory it received as `global`), nor pin a
    # forged grant with a far-future clock. So: reject a future acl clock, and
    # from an untrusted peer accept the incoming visibility only if it is a
    # SUBSET of what we already have — a revoke shrinks and propagates, an
    # expansion is refused (the owner's own trusted node is the authority for
    # widening a grant). Trusted imports (local admin / own full replica) may
    # converge freely.
    ex_acl = existing["acl_updated_at"]
    acl_distance = stamp_distance_to_stamp_seconds(inc_acl, ex_acl)
    acl_wins = acl_distance > 0 or (
        acl_distance == 0
        and (entry.get("visibility") or "") > (existing["visibility"] or "")
    )
    if acl_wins and not _stamp_too_future(inc_acl) and _acl_change_allowed(
        entry.get("visibility"), existing["visibility"], trusted
    ):
        store.conn.execute(
            "UPDATE memories SET visibility = ?, acl_updated_at = ? WHERE id = ?",
            (entry.get("visibility"), inc_acl, entry["id"]),
        )
        changed = True
    stats["memories_updated" if changed else "memories_skipped"] += 1


def _acl_change_allowed(incoming_vis, existing_vis, trusted: bool) -> bool:
    """A trusted import may set any visibility; an untrusted peer may only SHRINK
    it (propagate a revoke), never widen it (block visibility escalation)."""
    if trusted:
        return True
    try:
        inc = set(json.loads(incoming_vis) if isinstance(incoming_vis, str) else (incoming_vis or []))
        ex = set(json.loads(existing_vis) if isinstance(existing_vis, str) else (existing_vis or []))
    except (ValueError, TypeError):
        return False  # unparseable ACL from an untrusted peer — refuse
    return inc <= ex


def _tag_source(source, peer: str | None) -> str:
    """Record sync provenance in the memory's source JSON."""
    if not peer:
        return source if isinstance(source, str) else json.dumps(source or {})
    try:
        data = json.loads(source) if isinstance(source, str) else dict(source or {})
    except (ValueError, TypeError):
        data = {}
    data["synced_from"] = peer
    return json.dumps(data, ensure_ascii=False)


def _apply_tombstone(store, entry: dict, stats: dict) -> None:
    mem_id = entry["id"]
    deleted_at = entry["deleted_at"]
    row = store.conn.execute(
        "SELECT updated_at FROM memories WHERE id = ?", (mem_id,)
    ).fetchone()
    if row is not None and (
        stamp_distance_to_stamp_seconds(deleted_at, row["updated_at"]) >= 0
    ):
        store.conn.execute("DELETE FROM memory_links WHERE src_id = ? OR dst_id = ?", (mem_id, mem_id))
        store.conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        stats["tombstones_applied"] += 1
    # Keep the tombstone locally so it re-propagates and blocks a later re-add.
    store.conn.execute(
        "INSERT INTO tombstones(id, deleted_at) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET deleted_at = "
        "CASE WHEN excluded.deleted_at > tombstones.deleted_at "
        "THEN excluded.deleted_at ELSE tombstones.deleted_at END",
        (mem_id, deleted_at),
    )


def _clean_members(value) -> list[str]:
    """Coerce a bundle's `members` field to a clean list of id strings.

    Defends against a malformed bundle where members is a bare string (which
    would iterate into per-character garbage members) or contains non-strings.
    """
    if not isinstance(value, list):
        return []
    return [str(m) for m in value if isinstance(m, (str, int)) and str(m)]


def _org_tomb_at(store, kind: str, id_: str) -> str | None:
    row = store.conn.execute(
        "SELECT deleted_at FROM org_tombstones WHERE kind = ? AND id = ?", (kind, id_)
    ).fetchone()
    return row[0] if row else None


def _project_version_would_merge(store, entry: dict) -> bool:
    """Whether a project version survives its tombstone and LWW checks."""
    pid = entry["id"]
    upd = entry["updated_at"]
    tomb = _org_tomb_at(store, "project", pid)
    if tomb is not None and stamp_distance_to_stamp_seconds(tomb, upd) >= 0:
        return False
    existing = store.conn.execute(
        "SELECT updated_at FROM projects WHERE id = ?",
        (pid,),
    ).fetchone()
    if existing is None:
        return True
    update_distance = stamp_distance_to_stamp_seconds(
        upd,
        existing["updated_at"],
    )
    if update_distance < 0:
        return False
    if update_distance > 0:
        return True
    members = _clean_members(entry.get("members"))
    existing_members = [
        row[0]
        for row in store.conn.execute(
            "SELECT agent_id FROM project_members WHERE project_id = ?",
            (pid,),
        ).fetchall()
    ]
    return _org_member_wins(members, existing_members)


def _merge_team(
    store,
    entry: dict,
    stats: dict,
    *,
    org_scope: str | None,
    project_parent: tuple[str, frozenset[str]] | None = None,
) -> None:
    """Converge a team's definition + full member set by last-writer-wins on
    updated_at; a member set REPLACE means removals propagate too.

    Gated: only a peer authorized for this team (org_scope 'full' or
    'team:<this id>') may rewrite it, and an implausibly future-dated record is
    rejected so it cannot win LWW forever.
    """
    tid = entry["id"]
    upd = entry["updated_at"]
    if not _org_scope_allows(
        org_scope,
        "team",
        tid,
        team_of=None,
        project_parent=project_parent,
        asserted_members=entry.get("members"),
    ):
        stats["org_records_rejected"] += 1
        return
    if _stamp_too_future(upd):
        stats["org_records_rejected"] += 1
        return
    tomb = _org_tomb_at(store, "team", tid)
    if tomb is not None and (
        stamp_distance_to_stamp_seconds(tomb, upd) >= 0
    ):
        return  # deleted at/after this version — don't resurrect
    members = _clean_members(entry.get("members"))
    existing = store.conn.execute("SELECT updated_at FROM teams WHERE id = ?", (tid,)).fetchone()
    if existing is not None:
        update_distance = stamp_distance_to_stamp_seconds(
            upd,
            existing["updated_at"],
        )
        if update_distance < 0:
            return
        if update_distance == 0:
            # Same instant on both nodes: converge deterministically instead of
            # each keeping its own member set.
            ex_members = [r[0] for r in store.conn.execute(
                "SELECT agent_id FROM team_members WHERE team_id = ?", (tid,)
            ).fetchall()]
            if not _org_member_wins(members, ex_members):
                return
    store.conn.execute(
        "INSERT INTO teams(id, name, created_at, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at",
        (tid, entry.get("name") or tid, upd, upd),
    )
    store.conn.execute("DELETE FROM team_members WHERE team_id = ?", (tid,))
    for agent_id in members:
        store.conn.execute(
            "INSERT OR IGNORE INTO team_members(team_id, agent_id) VALUES (?, ?)", (tid, agent_id)
        )
    # Subset invariant on import: a project member must still be a team member.
    # After replacing the team roster, drop project members no longer in it.
    store.conn.execute(
        "DELETE FROM project_members WHERE project_id IN "
        "(SELECT id FROM projects WHERE team_id = ?) AND agent_id NOT IN "
        "(SELECT agent_id FROM team_members WHERE team_id = ?)",
        (tid, tid),
    )
    stats["teams_upserted"] += 1


def _merge_project(store, entry: dict, stats: dict, *, org_scope: str | None) -> None:
    pid = entry["id"]
    upd = entry["updated_at"]
    team_id = entry.get("team_id") or ""
    # A team-scoped peer may assert a project only if it belongs to that team;
    # trust the record's team_id, falling back to the local parent when absent.
    parent = team_id
    if not parent:
        row = store.conn.execute(
            "SELECT team_id FROM projects WHERE id = ?", (pid,)
        ).fetchone()
        parent = row[0] if row else None
    if not _org_scope_allows(org_scope, "project", pid, team_of=parent):
        stats["org_records_rejected"] += 1
        return
    if _stamp_too_future(upd):
        stats["org_records_rejected"] += 1
        return
    if not _project_version_would_merge(store, entry):
        return
    members = _clean_members(entry.get("members"))
    store.conn.execute(
        "INSERT INTO projects(id, team_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at",
        (pid, team_id, entry.get("name") or pid, upd, upd),
    )
    store.conn.execute("DELETE FROM project_members WHERE project_id = ?", (pid,))
    for agent_id in members:
        # Preserve the subset invariant even if the team member set is out of
        # sync: only keep project members who are current team members.
        is_member = store.conn.execute(
            "SELECT 1 FROM team_members WHERE team_id = ? AND agent_id = ?", (team_id, agent_id)
        ).fetchone()
        if is_member:
            store.conn.execute(
                "INSERT OR IGNORE INTO project_members(project_id, agent_id) VALUES (?, ?)",
                (pid, agent_id),
            )
    stats["projects_upserted"] += 1


def _apply_org_tombstone(store, entry: dict, stats: dict, *, org_scope: str | None) -> None:
    kind, id_ = entry["tomb_kind"], entry["id"]
    deleted_at = entry["deleted_at"]
    # Authorize against the peer's scope. For a project tombstone under a
    # team-scoped peer, resolve the parent team locally.
    parent = None
    if kind == "project":
        row = store.conn.execute("SELECT team_id FROM projects WHERE id = ?", (id_,)).fetchone()
        parent = row[0] if row else None
    if not _org_scope_allows(org_scope, kind, id_, team_of=parent):
        stats["org_records_rejected"] += 1
        return
    if _stamp_too_future(deleted_at):
        stats["org_records_rejected"] += 1
        return
    if kind == "team":
        row = store.conn.execute("SELECT updated_at FROM teams WHERE id = ?", (id_,)).fetchone()
        if row is not None and (
            stamp_distance_to_stamp_seconds(deleted_at, row["updated_at"]) >= 0
        ):
            for pr in store.conn.execute("SELECT id FROM projects WHERE team_id = ?", (id_,)).fetchall():
                store.conn.execute("DELETE FROM project_members WHERE project_id = ?", (pr[0],))
                store._strip_visibility_grant(f"project:{pr[0]}")
            store.conn.execute("DELETE FROM projects WHERE team_id = ?", (id_,))
            store.conn.execute("DELETE FROM team_members WHERE team_id = ?", (id_,))
            store.conn.execute("DELETE FROM teams WHERE id = ?", (id_,))
            store._strip_visibility_grant(f"team:{id_}")
            stats["org_tombstones_applied"] += 1
    elif kind == "project":
        row = store.conn.execute("SELECT updated_at FROM projects WHERE id = ?", (id_,)).fetchone()
        if row is not None and (
            stamp_distance_to_stamp_seconds(deleted_at, row["updated_at"]) >= 0
        ):
            store.conn.execute("DELETE FROM project_members WHERE project_id = ?", (id_,))
            store.conn.execute("DELETE FROM projects WHERE id = ?", (id_,))
            store._strip_visibility_grant(f"project:{id_}")
            stats["org_tombstones_applied"] += 1
    store.conn.execute(
        "INSERT INTO org_tombstones(kind, id, deleted_at) VALUES (?, ?, ?) "
        "ON CONFLICT(kind, id) DO UPDATE SET deleted_at = "
        "CASE WHEN excluded.deleted_at > org_tombstones.deleted_at "
        "THEN excluded.deleted_at ELSE org_tombstones.deleted_at END",
        (kind, id_, deleted_at),
    )


def _merge_link(store, entry: dict, stats: dict) -> None:
    # Only keep links whose endpoints exist after the memory merge pass;
    # bundles list memories before links, so ordering is already safe.
    endpoints = store.conn.execute(
        "SELECT COUNT(*) FROM memories WHERE id IN (?, ?)",
        (entry["src_id"], entry["dst_id"]),
    ).fetchone()[0]
    if endpoints != 2:
        return
    entry = dict(entry)
    existing = store.conn.execute(
        "SELECT weight, activation_count, last_activated_at FROM memory_links "
        "WHERE src_id = ? AND dst_id = ? AND relation = ?",
        (entry["src_id"], entry["dst_id"], entry["relation"]),
    ).fetchone()
    if existing is None:
        columns = ", ".join(_LINK_KEYS)
        placeholders = ", ".join("?" for _ in _LINK_KEYS)
        store.conn.execute(
            f"INSERT INTO memory_links({columns}) VALUES ({placeholders})",
            [entry.get(key) for key in _LINK_KEYS],
        )
        stats["links_added"] += 1
    else:
        store.conn.execute(
            """
            UPDATE memory_links
            SET weight = max(weight, ?),
                activation_count = max(activation_count, ?),
                updated_at = max(updated_at, ?),
                last_activated_at = CASE
                    WHEN last_activated_at IS NULL THEN ?
                    WHEN ? IS NULL THEN last_activated_at
                    ELSE max(last_activated_at, ?)
                END
            WHERE src_id = ? AND dst_id = ? AND relation = ?
            """,
            (
                float(entry.get("weight") or 0.0),
                int(entry.get("activation_count") or 0),
                entry["updated_at"],
                entry.get("last_activated_at"),
                entry.get("last_activated_at"),
                entry.get("last_activated_at"),
                entry["src_id"], entry["dst_id"], entry["relation"],
            ),
        )
        stats["links_merged"] += 1


def _merge_profile(store, entry: dict, stats: dict) -> None:
    entry = dict(entry)
    existing = store.conn.execute(
        "SELECT updated_at FROM recall_profiles WHERE agent_id = ?", (entry["agent_id"],)
    ).fetchone()
    if existing is not None and (
        stamp_distance_to_stamp_seconds(
            entry["updated_at"],
            existing["updated_at"],
        )
        <= 0
    ):
        return
    store.conn.execute(
        """
        INSERT INTO recall_profiles(agent_id, type_weights, scope_weights, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(agent_id) DO UPDATE SET
          type_weights = excluded.type_weights,
          scope_weights = excluded.scope_weights,
          updated_at = excluded.updated_at
        """,
        (entry["agent_id"], entry["type_weights"], entry["scope_weights"], entry["updated_at"]),
    )
    stats["profiles_upserted"] += 1


def _export_kwargs_for_policy(policy: str) -> dict:
    """Translate a peer policy into export_bundle keyword arguments.

    A 'shared' peer gets memories but NO org structure (org membership is the
    whole node's ACL graph — not something a memory-only peer should learn).
    """
    if policy == "full":
        return {"include_private": True, "include_org": True}
    if policy.startswith("team:"):
        return {"team": policy[len("team:"):], "include_private": False, "include_org": True}
    if policy.startswith("project:"):
        return {"project": policy[len("project:"):], "include_private": False, "include_org": True}
    return {"include_private": False, "include_org": False}  # 'shared'/unknown: memories only


def _org_scope_for_policy(policy: str) -> str | None:
    """The org-mutation authorization a peer with this policy carries on IMPORT.

    Mirrors the export scope: 'full' may assert anything, a scoped peer only its
    own team/project, a 'shared' (or unknown) peer nothing.
    """
    if policy == "full":
        return "full"
    if policy.startswith(("team:", "project:")):
        return policy
    return None


def pull_from_peer(client, base_url: str, *, since: str | None = None,
                   peer_token: str | None = None, trusted: bool = True,
                   org_scope: str | None = None, lock=None) -> dict[str, int]:
    """Fetch a peer's bundle over HTTP (unlocked) and merge it locally (locked)."""
    import tempfile

    from . import crypto

    body = _http(base_url.rstrip("/") + "/api/sync/export"
                 + (f"?since={since}" if since else ""), token=peer_token)
    if crypto.is_encrypted(body):
        secret = crypto.load_sync_secret(getattr(client, "home", None))
        if not secret:
            raise crypto.SyncCryptoError(
                f"peer {base_url} returned an encrypted bundle but no "
                "AGENT_MEMORY_SYNC_KEY is configured on this node")
        body = crypto.decrypt_bundle(body, secret)
    # The bundle header (first line) carries the peer's node_name; capture it
    # so sync_with_peer can refresh the display name without a second request.
    peer_node_name = ""
    try:
        first_nl = body.find("\n")
        header = json.loads(body[:first_nl] if first_nl >= 0 else body)
        peer_node_name = str(header.get("node_name") or "").strip()
    except Exception:  # noqa: BLE001, S110 - header parse is best-effort.
        pass
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as handle:
        handle.write(body)
    try:
        with _guard(lock):
            counts = client.import_bundle(
                handle.name, source_peer=base_url.rstrip("/"),
                trusted=trusted, org_scope=org_scope,
            )
        if peer_node_name:
            counts["_peer_node_name"] = peer_node_name
        return counts
    finally:
        Path(handle.name).unlink(missing_ok=True)


def push_to_peer(client, base_url: str, *, since: str | None = None,
                 peer_token: str | None = None, policy: str = "shared", lock=None) -> dict[str, int]:
    """Export the local bundle (locked) and POST it to a peer (unlocked)."""
    export_kwargs = _export_kwargs_for_policy(policy)
    with tempfile.TemporaryDirectory() as directory:
        bundle_path = Path(directory) / "bundle.jsonl"
        with _guard(lock):
            client.export_bundle(bundle_path, since=since, **export_kwargs)
        payload = bundle_path.read_text(encoding="utf-8")
    from . import crypto

    secret = crypto.load_sync_secret(getattr(client, "home", None))
    if secret:
        payload = crypto.encrypt_bundle(payload, secret)
    response = _http(base_url.rstrip("/") + "/api/sync/import", token=peer_token, post=payload)
    return json.loads(response)


def sync_with_peer(client, url: str, *, peer_token: str | None = None,
                   policy: str = "shared", lock=None) -> dict[str, object]:
    """Bidirectional converge with one peer: pull their bundle, push ours.

    `policy` scopes BOTH directions: what we push, and how far we trust what
    we pull ('full' == own trusted node, so imports may add global memories).
    `lock`, when given, is held only around the local DB reads/writes, never
    across the peer HTTP round-trips.
    """
    trusted = policy == "full"
    pulled = pull_from_peer(
        client, url, peer_token=peer_token, trusted=trusted,
        org_scope=_org_scope_for_policy(policy), lock=lock,
    )
    pushed = push_to_peer(client, url, peer_token=peer_token, policy=policy, lock=lock)
    # Refresh the peer's display name from the node_name already carried in the
    # bundle header we just pulled — no extra /api/node round-trip. Node
    # renames otherwise never reach the peers that registered the old name.
    advertised = str(pulled.pop("_peer_node_name", "") or "")
    if advertised:
        with _guard(lock):
            client.store.update_peer_name(url, advertised)
    # Record on the registered peer (if any) so `agent-memory status` and the
    # console show real last_synced/last_result for EVERY sync path — direct
    # pull/push, join's first sync, and the mesh loop alike.
    with _guard(lock):
        client.store.record_peer_sync(
            url,
            f"ok +{pulled['memories_added']}/~{pulled['memories_updated']} pulled",
        )
    return {"peer": url, "pulled": pulled, "pushed": pushed, "ok": True}


def sync_all_peers(client, *, lock=None) -> list[dict[str, object]]:
    """Converge with every registered peer; failures are per-peer, not fatal.

    Pass `lock` (the server's shared-client lock) so DB access is serialized
    without the lock being held across any peer's HTTP round-trip.
    """
    results: list[dict[str, object]] = []
    with _guard(lock):
        peers = client.store.list_peers()
    for peer in peers:
        url = peer["url"]
        with _guard(lock):
            token = client.store.peer_token(url)
        try:
            result = sync_with_peer(
                client, url,
                peer_token=token,
                policy=peer.get("policy", "shared"),
                lock=lock,
            )
        except Exception as exc:  # noqa: BLE001 - one unreachable peer must not stop the mesh
            result = {"peer": url, "ok": False, "error": str(exc)}
            # Successes are recorded inside sync_with_peer; only failures here.
            client.store.record_peer_sync(url, f"error: {exc}")
        results.append(result)
    return results


def fetch_peer_node_name(url: str, *, token: str | None = None) -> str:
    """Ask a peer for its advertised node_name (empty string on any failure)."""
    try:
        body = _http(url.rstrip("/") + "/api/node", token=token)
        return str(json.loads(body).get("node_name") or "").strip()
    except Exception:  # noqa: BLE001 - identity is best-effort, never fatal to add-peer
        return ""


def _http(url: str, *, token: str | None, post: str | None = None) -> str:
    import ssl
    import urllib.error
    import urllib.request

    if not url.startswith(("http://", "https://")):
        raise ValueError("peer URL must start with http:// or https://")
    request = urllib.request.Request(
        url,
        data=post.encode("utf-8") if post is not None else None,
        method="POST" if post is not None else "GET",
        headers={"Content-Type": "application/x-ndjson"},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    # Explicit, certificate-verifying TLS context for https peers (hostname
    # check + system trust store). http:// peers are unaffected; confidentiality
    # over plain HTTP comes from the app-layer bundle encryption instead.
    context = ssl.create_default_context() if url.startswith("https://") else None
    try:
        with urllib.request.urlopen(
            request,
            timeout=SYNC_HTTP_TIMEOUT_SECONDS,
            context=context,
        ) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = body
        if body:
            try:
                decoded = json.loads(body)
                if isinstance(decoded, dict) and decoded.get("detail"):
                    detail = str(decoded["detail"])
            except (TypeError, ValueError):
                pass
        message = str(exc)
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc
