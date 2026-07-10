"""Federated sync, first form: portable JSONL bundles.

`export_bundle` writes memories, links, and recall profiles as one JSONL file;
`import_bundle` merges a bundle into another store with deterministic conflict
resolution:

- memories: last-writer-wins on `updated_at` (stable ids are the identity)
- links: merged keeping the strongest weight, highest activation count, and
  latest activation timestamp
- profiles: last-writer-wins on `updated_at`

Move the bundle however you like — rsync, git, a USB stick. Peer-to-peer
online sync builds on the same merge rules later.
"""

from __future__ import annotations

import json
from pathlib import Path

BUNDLE_VERSION = 1
_MEMORY_KEYS = (
    "id", "owner", "scope", "type", "content", "summary", "tags", "visibility",
    "source", "confidence", "importance", "created_at", "updated_at",
    "expires_at", "decay_policy", "decay_half_life_days", "last_accessed_at",
    "access_count", "pinned", "helpful_count", "unhelpful_count",
)
_LINK_KEYS = (
    "src_id", "dst_id", "relation", "weight", "created_at", "updated_at",
    "last_activated_at", "activation_count", "source",
)


def export_bundle(
    store, path: str | Path, *, since: str | None = None, team: str | None = None
) -> dict[str, int]:
    """Write a bundle; `team` restricts it to one project/team's shared memory.

    A team-scoped bundle carries only memories granted to that team, links
    whose BOTH endpoints are in the bundle, and the recall profiles of that
    team's registered members — a portable "project memory" unit.
    """
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"memories": 0, "links": 0, "profiles": 0}
    clauses, params = [], []
    if since:
        clauses.append("updated_at > ?")
        params.append(since)
    if team:
        clauses.append(
            "(EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = ?)"
            " OR EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = 'team'"
            "            AND json_extract(source, '$.team_id') = ?))"
        )
        params.extend([f"team:{team}", team])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    exported_ids: set[str] = set()
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "bundle", "version": BUNDLE_VERSION}) + "\n")
        for row in store.conn.execute(f"SELECT * FROM memories {where}", params):
            payload = {key: row[key] for key in _MEMORY_KEYS}
            exported_ids.add(row["id"])
            handle.write(json.dumps({"kind": "memory", **payload}, ensure_ascii=False) + "\n")
            counts["memories"] += 1
        link_where, link_params = ("WHERE updated_at > ?", [since]) if since else ("", [])
        for row in store.conn.execute(f"SELECT * FROM memory_links {link_where}", link_params):
            if team and not (row["src_id"] in exported_ids and row["dst_id"] in exported_ids):
                continue
            payload = {key: row[key] for key in _LINK_KEYS}
            handle.write(json.dumps({"kind": "link", **payload}, ensure_ascii=False) + "\n")
            counts["links"] += 1
        members = None
        if team:
            members = {
                agent["id"] for agent in store.list_agents() if team in agent["teams"]
            }
        for row in store.conn.execute("SELECT * FROM recall_profiles"):
            if members is not None and row["agent_id"] not in members:
                continue
            handle.write(json.dumps({"kind": "profile", **dict(row)}, ensure_ascii=False) + "\n")
            counts["profiles"] += 1
    return counts


def import_bundle(store, path: str | Path) -> dict[str, int]:
    path = Path(path).expanduser()
    stats = {
        "memories_added": 0, "memories_updated": 0, "memories_skipped": 0,
        "links_added": 0, "links_merged": 0, "profiles_upserted": 0,
    }
    with path.open("r", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        if header.get("kind") != "bundle" or header.get("version") != BUNDLE_VERSION:
            raise ValueError("not a compatible agent-memory-os bundle")
        for line in handle:
            entry = json.loads(line)
            kind = entry.pop("kind")
            if kind == "memory":
                _merge_memory(store, entry, stats)
            elif kind == "link":
                _merge_link(store, entry, stats)
            elif kind == "profile":
                _merge_profile(store, entry, stats)
    store.conn.commit()
    return stats


def _merge_memory(store, entry: dict, stats: dict) -> None:
    existing = store.conn.execute(
        "SELECT updated_at FROM memories WHERE id = ?", (entry["id"],)
    ).fetchone()
    columns = ", ".join(_MEMORY_KEYS)
    placeholders = ", ".join("?" for _ in _MEMORY_KEYS)
    values = [entry.get(key) for key in _MEMORY_KEYS]
    if existing is None:
        store.conn.execute(
            f"INSERT INTO memories({columns}) VALUES ({placeholders})", values
        )
        stats["memories_added"] += 1
    elif (entry.get("updated_at") or "") > existing["updated_at"]:
        assignments = ", ".join(f"{key} = ?" for key in _MEMORY_KEYS if key != "id")
        store.conn.execute(
            f"UPDATE memories SET {assignments} WHERE id = ?",
            [entry.get(key) for key in _MEMORY_KEYS if key != "id"] + [entry["id"]],
        )
        stats["memories_updated"] += 1
    else:
        stats["memories_skipped"] += 1


def _merge_link(store, entry: dict, stats: dict) -> None:
    # Only keep links whose endpoints exist after the memory merge pass;
    # bundles list memories before links, so ordering is already safe.
    endpoints = store.conn.execute(
        "SELECT COUNT(*) FROM memories WHERE id IN (?, ?)",
        (entry["src_id"], entry["dst_id"]),
    ).fetchone()[0]
    if endpoints != 2:
        return
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
                last_activated_at = max(COALESCE(last_activated_at, ''), COALESCE(?, ''))
            WHERE src_id = ? AND dst_id = ? AND relation = ?
            """,
            (
                float(entry.get("weight") or 0.0),
                int(entry.get("activation_count") or 0),
                entry.get("last_activated_at"),
                entry["src_id"], entry["dst_id"], entry["relation"],
            ),
        )
        stats["links_merged"] += 1


def pull_from_peer(client, base_url: str, *, since: str | None = None,
                   peer_token: str | None = None) -> dict[str, int]:
    """Fetch a peer's bundle over HTTP and merge it locally."""
    import tempfile

    body = _http(base_url.rstrip("/") + "/api/sync/export"
                 + (f"?since={since}" if since else ""), token=peer_token)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
        handle.write(body)
    try:
        return client.import_bundle(handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def push_to_peer(client, base_url: str, *, since: str | None = None,
                 peer_token: str | None = None) -> dict[str, int]:
    """Export the local bundle and merge it into a peer over HTTP."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
        client.export_bundle(handle.name, since=since)
    try:
        payload = Path(handle.name).read_text(encoding="utf-8")
    finally:
        Path(handle.name).unlink(missing_ok=True)
    response = _http(base_url.rstrip("/") + "/api/sync/import", token=peer_token, post=payload)
    return json.loads(response)


def sync_with_peer(client, url: str, *, peer_token: str | None = None) -> dict[str, object]:
    """Bidirectional converge with one peer: pull their bundle, push ours."""
    pulled = pull_from_peer(client, url, peer_token=peer_token)
    pushed = push_to_peer(client, url, peer_token=peer_token)
    return {"peer": url, "pulled": pulled, "pushed": pushed, "ok": True}


def sync_all_peers(client) -> list[dict[str, object]]:
    """Converge with every registered peer; failures are per-peer, not fatal."""
    results: list[dict[str, object]] = []
    for peer in client.store.list_peers():
        url = peer["url"]
        try:
            result = sync_with_peer(client, url, peer_token=client.store.peer_token(url))
            summary = (
                f"ok +{result['pulled']['memories_added']}/"
                f"~{result['pulled']['memories_updated']} pulled"
            )
        except Exception as exc:  # noqa: BLE001 - one unreachable peer must not stop the mesh
            result = {"peer": url, "ok": False, "error": str(exc)}
            summary = f"error: {exc}"
        client.store.record_peer_sync(url, summary)
        results.append(result)
    return results


def _http(url: str, *, token: str | None, post: str | None = None) -> str:
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
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _merge_profile(store, entry: dict, stats: dict) -> None:
    existing = store.conn.execute(
        "SELECT updated_at FROM recall_profiles WHERE agent_id = ?", (entry["agent_id"],)
    ).fetchone()
    if existing is not None and (entry.get("updated_at") or "") <= existing["updated_at"]:
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
