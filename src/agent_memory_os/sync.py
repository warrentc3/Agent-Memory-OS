"""Federated sync: portable JSONL bundles + peer transport.

`export_bundle` writes memories, links, recall profiles, and tombstones as one
JSONL file; `import_bundle` merges a bundle into another store with
deterministic, convergent conflict resolution:

- memories: last-writer-wins on normalized `updated_at`, with a content
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
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path


def _guard(lock):
    """Hold `lock` around a DB operation, or nothing when called single-threaded.

    Peer HTTP round-trips must run OUTSIDE this so a slow/unreachable peer never
    freezes every other request on a shared server connection.
    """
    return lock if lock is not None else nullcontext()

BUNDLE_VERSION = 2
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


def _norm_ts(value: str | None) -> str:
    """Canonicalize an ISO-8601 timestamp for LWW comparison.

    Normalizes a 'Z' suffix and offset spelling so '...Z' and '...+00:00'
    (which compare wrong lexicographically) resolve to the same instant.
    Unparseable/empty input sorts before everything.
    """
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _incoming_wins(inc_ts: str, inc_content: str, ex_ts: str, ex_content: str) -> bool:
    """LWW with a deterministic tie-break, so both nodes converge identically."""
    inc_n, ex_n = _norm_ts(inc_ts), _norm_ts(ex_ts)
    if inc_n != ex_n:
        return inc_n > ex_n
    return inc_content > ex_content  # same instant: larger content wins, deterministically


def export_bundle(
    store,
    path: str | Path,
    *,
    since: str | None = None,
    team: str | None = None,
    include_private: bool = True,
) -> dict[str, int]:
    """Write a bundle.

    `team` restricts it to one project/team's shared memory. `include_private`
    (default True) controls whether private `visibility=[]` memories are
    written — peer sync passes False for any non-'full' peer so private memory
    never leaves the machine. Tombstones are always included (an id + timestamp
    carry no content).
    """
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"memories": 0, "links": 0, "profiles": 0, "tombstones": 0}
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
    if not include_private:
        # Private == empty visibility array. Keep only rows granted to someone.
        clauses.append("json_array_length(visibility) > 0")
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
            # A link is only meaningful if both endpoints are in the bundle;
            # this also stops a link from revealing a filtered-out private id.
            if not (row["src_id"] in exported_ids and row["dst_id"] in exported_ids):
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
        for mem_id, deleted_at in store.list_tombstones(since=since):
            handle.write(
                json.dumps({"kind": "tombstone", "id": mem_id, "deleted_at": deleted_at}) + "\n"
            )
            counts["tombstones"] += 1
    return counts


def import_bundle(
    store,
    path: str | Path,
    *,
    source_peer: str | None = None,
    trusted: bool = True,
) -> dict[str, int]:
    """Merge a bundle into the store.

    `trusted=False` (a semi-trusted 'shared'/'team' peer) forbids injecting
    NEW globally-visible memories and records `source.synced_from`. The whole
    merge is atomic: a corrupt line rolls everything back.
    """
    path = Path(path).expanduser()
    stats = {
        "memories_added": 0, "memories_updated": 0, "memories_skipped": 0,
        "links_added": 0, "links_merged": 0, "profiles_upserted": 0,
        "tombstones_applied": 0,
    }
    # A semi-trusted peer must not forge a memory authored by one of OUR local
    # agents (impersonation). Compute the guarded id set once.
    local_agents = set() if trusted else {a["id"] for a in store.list_agents()}
    try:
        with path.open("r", encoding="utf-8") as handle:
            header = json.loads(handle.readline())
            if header.get("kind") != "bundle" or header.get("version") not in (1, 2):
                raise ValueError("not a compatible agent-memory-os bundle")
            for line in handle:
                entry = json.loads(line)
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
    except Exception:
        store.conn.rollback()
        raise
    store.conn.commit()
    return stats


def _merge_memory(store, entry: dict, stats: dict, *, source_peer=None,
                  trusted=True, local_agents=frozenset()) -> None:
    # A deletion that happened at or after this version wins over the re-add.
    tomb = store.tombstone_for(entry["id"])
    if tomb is not None and _norm_ts(tomb) >= _norm_ts(entry.get("updated_at")):
        stats["memories_skipped"] += 1
        return

    existing = store.conn.execute(
        "SELECT updated_at, content FROM memories WHERE id = ?", (entry["id"],)
    ).fetchone()

    if not trusted:
        # Anti-impersonation: a semi-trusted peer cannot stand up a NEW memory
        # authored by one of our local agents. Genuine shared/global memory
        # under the peer's own owner ids still flows; every import records its
        # origin in source.synced_from so it is never mistaken for local.
        if existing is None and entry.get("owner") in local_agents:
            stats["memories_skipped"] += 1
            return
        entry = dict(entry)
        entry["source"] = _tag_source(entry.get("source"), source_peer)

    columns = ", ".join(_MEMORY_KEYS)
    placeholders = ", ".join("?" for _ in _MEMORY_KEYS)
    if existing is None:
        store.conn.execute(
            f"INSERT INTO memories({columns}) VALUES ({placeholders})",
            [entry.get(key) for key in _MEMORY_KEYS],
        )
        stats["memories_added"] += 1
    elif _incoming_wins(
        entry.get("updated_at"), entry.get("content") or "",
        existing["updated_at"], existing["content"] or "",
    ):
        assignments = ", ".join(f"{key} = ?" for key in _MEMORY_KEYS if key != "id")
        store.conn.execute(
            f"UPDATE memories SET {assignments} WHERE id = ?",
            [entry.get(key) for key in _MEMORY_KEYS if key != "id"] + [entry["id"]],
        )
        stats["memories_updated"] += 1
    else:
        stats["memories_skipped"] += 1


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
    mem_id, deleted_at = entry["id"], entry.get("deleted_at") or ""
    row = store.conn.execute(
        "SELECT updated_at FROM memories WHERE id = ?", (mem_id,)
    ).fetchone()
    if row is not None and _norm_ts(deleted_at) >= _norm_ts(row["updated_at"]):
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


def _merge_profile(store, entry: dict, stats: dict) -> None:
    existing = store.conn.execute(
        "SELECT updated_at FROM recall_profiles WHERE agent_id = ?", (entry["agent_id"],)
    ).fetchone()
    if existing is not None and _norm_ts(entry.get("updated_at")) <= _norm_ts(existing["updated_at"]):
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
    """Translate a peer policy into export_bundle keyword arguments."""
    if policy == "full":
        return {"include_private": True}
    if policy.startswith("team:"):
        return {"team": policy[len("team:"):], "include_private": False}
    return {"include_private": False}  # 'shared' and any unknown value: safe default


def pull_from_peer(client, base_url: str, *, since: str | None = None,
                   peer_token: str | None = None, trusted: bool = True, lock=None) -> dict[str, int]:
    """Fetch a peer's bundle over HTTP (unlocked) and merge it locally (locked)."""
    import tempfile

    body = _http(base_url.rstrip("/") + "/api/sync/export"
                 + (f"?since={since}" if since else ""), token=peer_token)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as handle:
        handle.write(body)
    try:
        with _guard(lock):
            return client.import_bundle(handle.name, source_peer=base_url.rstrip("/"), trusted=trusted)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def push_to_peer(client, base_url: str, *, since: str | None = None,
                 peer_token: str | None = None, policy: str = "shared", lock=None) -> dict[str, int]:
    """Export the local bundle (locked) and POST it to a peer (unlocked)."""
    import tempfile

    export_kwargs = _export_kwargs_for_policy(policy)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as handle:
        with _guard(lock):
            client.export_bundle(handle.name, since=since, **export_kwargs)
    try:
        payload = Path(handle.name).read_text(encoding="utf-8")
    finally:
        Path(handle.name).unlink(missing_ok=True)
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
    pulled = pull_from_peer(client, url, peer_token=peer_token, trusted=trusted, lock=lock)
    pushed = push_to_peer(client, url, peer_token=peer_token, policy=policy, lock=lock)
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
