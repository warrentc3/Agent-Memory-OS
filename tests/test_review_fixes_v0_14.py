"""Regression tests for the v0.14 code+security review findings.

Each test pins one fixed vulnerability/bug so it cannot silently return. See
docs/reviews/20260712-v0.14.0-review.md for the findings these map to.
"""

from __future__ import annotations

import json

from agent_memory_os import MemoryClient
from agent_memory_os.sync import export_bundle, import_bundle
from agent_memory_os.timestamp_converters import dt_to_stamp, utc_now_dt


def _write_bundle(path, *entries, version=3):
    """Write an incoming sync-bundle fixture for the requested wire version.

    This test-only helper can represent historical peer input. It is not the
    production ``export_bundle()``, which validates and writes only current v4
    bundles.
    """
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "bundle", "version": version}) + "\n")
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _future():  # a timestamp far enough ahead to (previously) win LWW forever
    return "9999-12-31T23:59:59+00:00"


def _now():  # a legitimate, not-rejected current timestamp
    return dt_to_stamp(utc_now_dt())


# ---- H1: org merges must honour the peer's trust scope ----

def test_untrusted_push_cannot_forge_membership(tmp_path):
    """org_scope=None (an anonymous push / 'shared' peer) applies NO org records.

    Lineage:
    main: introduced bc2608c9@db-schema-v14.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    c = MemoryClient(home=tmp_path)
    c.store.create_team("finance")  # exists locally, attacker NOT a member
    bundle = tmp_path / "evil.jsonl"
    _write_bundle(bundle, {
        "kind": "team", "id": "finance", "name": "finance",
        "updated_at": _future(), "members": ["attacker"],
    })
    stats = import_bundle(c.store, str(bundle), trusted=False, org_scope=None)
    assert stats["org_records_rejected"] == 1
    assert "attacker" not in [m for m in c.store.get_team("finance")["members"]]


def test_team_scoped_peer_cannot_touch_other_team(tmp_path):
    """A 'team:alpha' peer may assert team alpha but not team beta.

    Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    c.store.create_team("alpha"); c.store.create_team("beta")
    # Bump both so the incoming records win LWW on merit, not on being newer.
    ts = _now()
    c.store.conn.execute("UPDATE teams SET updated_at = ? WHERE id IN ('alpha','beta')",
                         ("2020-01-01T00:00:00.000000Z",))
    c.store.conn.commit()
    bundle = tmp_path / "b.jsonl"
    _write_bundle(
        bundle,
        {"kind": "team", "id": "alpha", "name": "alpha", "updated_at": ts, "members": ["a1"]},
        {"kind": "team", "id": "beta", "name": "beta", "updated_at": ts, "members": ["intruder"]},
    )
    stats = import_bundle(c.store, str(bundle), trusted=False, org_scope="team:alpha")
    assert "a1" in c.store.get_team("alpha")["members"]          # own scope applied
    assert "intruder" not in c.store.get_team("beta")["members"]  # other scope rejected
    assert stats["org_records_rejected"] == 1


def test_untrusted_org_tombstone_cannot_wipe_team(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    c.store.create_team("keep"); c.store.add_team_member("keep", "a1")
    bundle = tmp_path / "t.jsonl"
    _write_bundle(bundle, {
        "kind": "org_tombstone", "tomb_kind": "team", "id": "keep", "deleted_at": _future(),
    })
    import_bundle(c.store, str(bundle), trusted=False, org_scope=None)
    assert c.store.get_team("keep") is not None  # not deleted by an untrusted push


# ---- H2: future-dated org records are rejected even from an authorized peer ----

def test_future_dated_org_record_rejected(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    c.store.create_team("t"); c.store.add_team_member("t", "real")
    bundle = tmp_path / "f.jsonl"
    _write_bundle(bundle, {
        "kind": "team", "id": "t", "name": "t", "updated_at": _future(), "members": ["forged"],
    })
    stats = import_bundle(c.store, str(bundle), trusted=True, org_scope="full")
    assert stats["org_records_rejected"] == 1
    assert c.store.get_team("t")["members"] == ["real"]  # unchanged


# ---- H4: equal-timestamp member sets converge deterministically ----

def test_equal_timestamp_membership_converges(tmp_path):
    """Two nodes editing the same team in the same second must converge to the
    SAME member set, not each keep its own.

    Lineage:
    main: introduced bc2608c9@db-schema-v14.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    ts = _now()

    def node_with(members):
        c = MemoryClient(home=tmp_path / f"n{hash(tuple(members)) & 0xffff}")
        c.store.create_team("shared")
        c.store.conn.execute("UPDATE teams SET updated_at = ? WHERE id = 'shared'", (ts,))
        for m in members:
            c.store.conn.execute(
                "INSERT OR IGNORE INTO team_members(team_id, agent_id) VALUES ('shared', ?)", (m,))
        c.store.conn.commit()
        return c

    a = node_with(["x", "z"])   # node A
    b = node_with(["y"])        # node B, same timestamp
    rec_a = {"kind": "team", "id": "shared", "name": "shared", "updated_at": ts,
             "members": ["x", "z"]}
    rec_b = {"kind": "team", "id": "shared", "name": "shared", "updated_at": ts,
             "members": ["y"]}
    ba = tmp_path / "ba.jsonl"; _write_bundle(ba, rec_b)
    ab = tmp_path / "ab.jsonl"; _write_bundle(ab, rec_a)
    import_bundle(a.store, str(ba), org_scope="full")  # A receives B
    import_bundle(b.store, str(ab), org_scope="full")  # B receives A
    assert a.store.get_team("shared")["members"] == b.store.get_team("shared")["members"]


# ---- M2: a 'shared' peer must not receive the org membership graph ----

def test_shared_export_omits_org_structure(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("a1"); c.store.create_team("secret")
    c.store.add_team_member("secret", "a1")
    out = tmp_path / "shared.jsonl"
    export_bundle(c.store, out, include_private=False, include_org=False)
    kinds = {json.loads(line)["kind"] for line in out.read_text().splitlines()}
    assert "team" not in kinds and "project" not in kinds and "org_tombstone" not in kinds


# ---- M3: project-scoped export narrows the parent-team roster ----

def test_project_export_does_not_leak_team_roster(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    for a in ("alice", "bob", "carol"):
        c.store.register_agent(a)
    c.store.create_team("eng")
    for a in ("alice", "bob", "carol"):
        c.store.add_team_member("eng", a)
    c.store.create_project("proj", "eng")
    c.store.add_project_member("proj", "alice")  # only alice is in the project
    out = tmp_path / "proj.jsonl"
    export_bundle(c.store, out, project="proj", include_private=False, include_org=True)
    team_rec = next(json.loads(l) for l in out.read_text().splitlines()
                    if json.loads(l).get("kind") == "team")
    # bob/carol are team members but NOT project members — must not leak.
    assert set(team_rec["members"]) == {"alice"}


def test_project_scope_accepts_only_validated_narrow_parent_team(tmp_path):
    src = MemoryClient(home=tmp_path / "src")
    for agent in ("alice", "bob"):
        src.store.register_agent(agent)
    src.store.create_team("eng")
    src.store.add_team_member("eng", "alice")
    src.store.add_team_member("eng", "bob")
    src.store.create_project("proj", "eng")
    src.store.add_project_member("proj", "alice")

    exported = tmp_path / "project.jsonl"
    export_bundle(
        src.store,
        exported,
        project="proj",
        include_private=False,
        include_org=True,
    )
    entries = [json.loads(line) for line in exported.read_text().splitlines()]
    team_entry = next(entry for entry in entries if entry["kind"] == "team")
    project_entry = next(entry for entry in entries if entry["kind"] == "project")

    dst = MemoryClient(home=tmp_path / "dst")
    accepted = import_bundle(dst.store, str(exported), org_scope="project:proj")

    assert accepted["teams_upserted"] == 1
    assert dst.store.get_team("eng")["members"] == ["alice"]
    assert dst.store.get_project("proj")["members"] == ["alice"]

    unrelated_bundle = tmp_path / "unrelated.jsonl"
    _write_bundle(
        unrelated_bundle,
        {**team_entry, "id": "other"},
        project_entry,
        version=4,
    )
    unrelated_dst = MemoryClient(home=tmp_path / "unrelated-dst")
    unrelated = import_bundle(
        unrelated_dst.store,
        str(unrelated_bundle),
        org_scope="project:proj",
    )
    assert unrelated["org_records_rejected"] == 1
    assert unrelated_dst.store.get_team("other") is None

    broader_bundle = tmp_path / "broader.jsonl"
    _write_bundle(
        broader_bundle,
        {**team_entry, "members": ["alice", "bob"]},
        project_entry,
        version=4,
    )
    broader_dst = MemoryClient(home=tmp_path / "broader-dst")
    broader = import_bundle(
        broader_dst.store,
        str(broader_bundle),
        org_scope="project:proj",
    )
    assert broader["org_records_rejected"] == 1
    assert broader_dst.store.get_team("eng") is None


def test_project_scope_uses_current_binding_for_parent_only_incremental(tmp_path):
    dst = MemoryClient(home=tmp_path / "dst")
    dst.store.register_agent("alice")
    dst.store.create_team("eng", name="Old name")
    dst.store.add_team_member("eng", "alice")
    dst.store.create_project("proj", "eng")
    dst.store.add_project_member("proj", "alice")
    dst.store.conn.execute(
        "UPDATE teams SET updated_at = ? WHERE id = ?",
        ("2026-08-10T11:00:00.000000Z", "eng"),
    )
    dst.store.conn.commit()

    incremental = tmp_path / "parent-only.jsonl"
    _write_bundle(
        incremental,
        {
            "kind": "team",
            "id": "eng",
            "name": "Current name",
            "updated_at": "2026-08-10T13:00:00.000000Z",
            "members": ["alice"],
        },
        version=4,
    )

    stats = import_bundle(
        dst.store,
        str(incremental),
        org_scope="project:proj",
    )

    assert stats["teams_upserted"] == 1
    assert dst.store.get_team("eng")["name"] == "Current name"
    assert dst.store.get_project("proj")["members"] == ["alice"]


def test_stale_project_record_cannot_authorize_parent_team(tmp_path):
    dst = MemoryClient(home=tmp_path / "dst")
    dst.store.register_agent("alice")
    dst.store.create_team("eng")
    dst.store.add_team_member("eng", "alice")
    dst.store.create_project("proj", "eng")
    dst.store.add_project_member("proj", "alice")
    dst.store.conn.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        ("2026-08-10T13:00:00.000000Z", "proj"),
    )
    dst.store.conn.commit()

    stale = tmp_path / "stale-project.jsonl"
    _write_bundle(
        stale,
        {
            "kind": "team",
            "id": "unrelated",
            "name": "unrelated",
            "updated_at": "2026-08-10T12:00:00.000000Z",
            "members": ["mallory"],
        },
        {
            "kind": "project",
            "id": "proj",
            "team_id": "unrelated",
            "name": "stale",
            "updated_at": "2026-08-10T11:00:00.000000Z",
            "members": ["mallory"],
        },
        version=4,
    )

    import_bundle(dst.store, str(stale), org_scope="project:proj")

    assert dst.store.get_team("unrelated") is None
    assert dst.store.get_project("proj")["team_id"] == "eng"
    assert dst.store.get_project("proj")["members"] == ["alice"]


def test_tombstoned_project_record_cannot_authorize_parent_team(tmp_path):
    dst = MemoryClient(home=tmp_path / "dst")
    dst.store.conn.execute(
        "INSERT INTO org_tombstones(kind, id, deleted_at) VALUES (?, ?, ?)",
        ("project", "retired", "2026-08-10T13:00:00.000000Z"),
    )
    dst.store.conn.commit()

    stale = tmp_path / "tombstoned-project.jsonl"
    _write_bundle(
        stale,
        {
            "kind": "team",
            "id": "unrelated",
            "name": "unrelated",
            "updated_at": "2026-08-10T12:00:00.000000Z",
            "members": ["mallory"],
        },
        {
            "kind": "project",
            "id": "retired",
            "team_id": "unrelated",
            "name": "retired",
            "updated_at": "2026-08-10T11:00:00.000000Z",
            "members": ["mallory"],
        },
        version=4,
    )

    import_bundle(dst.store, str(stale), org_scope="project:retired")

    assert dst.store.get_team("unrelated") is None
    assert dst.store.get_project("retired") is None


def test_newer_same_bundle_project_tombstone_blocks_parent_team(tmp_path):
    dst = MemoryClient(home=tmp_path / "dst")
    dst.store.register_agent("alice")
    bundle = tmp_path / "project-then-tombstone.jsonl"
    _write_bundle(
        bundle,
        {
            "kind": "team",
            "id": "eng",
            "name": "eng",
            "updated_at": "2026-08-10T11:00:00.000000Z",
            "members": ["alice"],
        },
        {
            "kind": "project",
            "id": "proj",
            "team_id": "eng",
            "name": "proj",
            "updated_at": "2026-08-10T11:00:00.000000Z",
            "members": ["alice"],
        },
        {
            "kind": "org_tombstone",
            "tomb_kind": "project",
            "id": "proj",
            "deleted_at": "2026-08-10T12:00:00.000000Z",
        },
        version=4,
    )

    stats = import_bundle(dst.store, str(bundle), org_scope="project:proj")

    assert stats["org_tombstones_applied"] == 1
    assert dst.store.get_project("proj") is None
    assert dst.store.get_team("eng") is None


def test_newer_same_bundle_project_tombstone_blocks_parent_only_mutation(tmp_path):
    dst = MemoryClient(home=tmp_path / "dst")
    for agent in ("alice", "bob"):
        dst.store.register_agent(agent)
    dst.store.create_team("eng", name="Original")
    dst.store.add_team_member("eng", "alice")
    dst.store.add_team_member("eng", "bob")
    dst.store.create_project("proj", "eng")
    dst.store.add_project_member("proj", "alice")
    dst.store.conn.execute(
        "UPDATE teams SET updated_at = ? WHERE id = ?",
        ("2026-08-10T10:00:00.000000Z", "eng"),
    )
    dst.store.conn.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        ("2026-08-10T11:00:00.000000Z", "proj"),
    )
    dst.store.conn.commit()

    bundle = tmp_path / "parent-then-tombstone.jsonl"
    _write_bundle(
        bundle,
        {
            "kind": "team",
            "id": "eng",
            "name": "Mutated",
            "updated_at": "2026-08-10T12:00:00.000000Z",
            "members": ["alice"],
        },
        {
            "kind": "org_tombstone",
            "tomb_kind": "project",
            "id": "proj",
            "deleted_at": "2026-08-10T13:00:00.000000Z",
        },
        version=4,
    )

    stats = import_bundle(dst.store, str(bundle), org_scope="project:proj")

    assert stats["org_tombstones_applied"] == 1
    assert dst.store.get_project("proj") is None
    assert dst.store.get_team("eng")["name"] == "Original"
    assert dst.store.get_team("eng")["members"] == ["alice", "bob"]


# ---- M5: deleting a team strips the bare-`team` grant (id-reuse can't resurrect) ----

def test_delete_team_strips_bare_team_grant(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("alice")
    c.store.create_team("X"); c.store.add_team_member("X", "alice")
    # A memory using the legacy bare-`team` scheme keyed by source.team_id.
    m = c.add("team secret", owner="ext", visibility=["team"], source={"team_id": "X"})
    c.store.delete_team("X")
    vis = json.loads(c.store.conn.execute(
        "SELECT visibility FROM memories WHERE id = ?", (m.id,)).fetchone()[0])
    assert "team" not in vis  # bare grant stripped; a reused id X can't resurrect access


# ---- B: revocation (and re-share) propagate over sync via the ACL clock ----

def test_revoke_share_propagates_over_sync(tmp_path):
    """A post-hoc revoke must retract already-synced access on the peer — without
    restarting the content/decay clock — and a later re-share must converge back.

    Lineage:
    main: introduced f2e8b453@db-schema-v15.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    src.store.register_agent("owner")
    src.store.create_team("t"); src.store.add_team_member("t", "owner")
    m = src.add("secret", owner="owner", visibility=["team:t", "global"])

    b1 = tmp_path / "b1.jsonl"; export_bundle(src.store, b1)
    import_bundle(dst.store, str(b1), org_scope="full")
    assert set(json.loads(_vis(dst, m.id))) == {"team:t", "global"}

    src.store.revoke_share(m.id, actor="owner", to_team="t")
    b2 = tmp_path / "b2.jsonl"; export_bundle(src.store, b2)
    import_bundle(dst.store, str(b2), org_scope="full")
    assert set(json.loads(_vis(dst, m.id))) == {"global"}          # revoke reached the peer
    assert src.store.get(m.id).updated_at == dst.store.get(m.id).updated_at  # decay clock intact

    src.store.share_memory(m.id, actor="owner", to_team="t")
    b3 = tmp_path / "b3.jsonl"; export_bundle(src.store, b3)
    import_bundle(dst.store, str(b3), org_scope="full")
    assert "team:t" in json.loads(_vis(dst, m.id))                  # re-share converges back


def test_older_acl_change_does_not_clobber_newer_local(tmp_path):
    """ACL LWW: an incoming visibility with an OLDER acl clock must not overwrite
    a newer local ACL (independent of the content clock).

    Lineage:
    main: introduced f2e8b453@db-schema-v15.
    """
    a = MemoryClient(home=tmp_path / "a")
    a.store.register_agent("o")
    m = a.add("x", owner="o", visibility=["global"])
    # Export the original (older ACL) state.
    b_old = tmp_path / "old.jsonl"; export_bundle(a.store, b_old)
    # Locally tighten to private (newer ACL clock).
    a.store.revoke_share(m.id, actor="o", to_agent=None) if False else a.store._set_visibility(m.id, [])
    # Re-importing the OLD bundle must NOT resurrect the "global" grant.
    import_bundle(a.store, str(b_old), org_scope="full")
    assert json.loads(_vis(a, m.id)) == []


def _vis(client, mem_id):
    return client.store.conn.execute(
        "SELECT visibility FROM memories WHERE id = ?", (mem_id,)).fetchone()[0]


def test_suggested_peer_policy_derivation(tmp_path):
    """Lineage:
    main: introduced f2e8b453@db-schema-v15.
    """
    c = MemoryClient(home=tmp_path)
    for a in ("solo", "multi", "proj", "none"):
        c.store.register_agent(a)
    c.store.create_team("t1"); c.store.create_team("t2")
    c.store.add_team_member("t1", "solo")                      # one team -> team:t1
    c.store.add_team_member("t1", "multi"); c.store.add_team_member("t2", "multi")  # two -> shared
    c.store.add_team_member("t1", "proj"); c.store.create_project("p1", "t1")
    c.store.add_project_member("p1", "proj")                   # one project -> project:p1
    assert c.store.suggested_peer_policy("solo")["policy"] == "team:t1"
    assert c.store.suggested_peer_policy("multi")["policy"] == "shared"
    assert c.store.suggested_peer_policy("proj")["policy"] == "project:p1"
    assert c.store.suggested_peer_policy("none")["policy"] == "shared"
    # It is advisory only and never 'full'.
    assert c.store.suggested_peer_policy("multi")["policy"] != "full"


# ---- v1.0 final-review fixes ----

def test_untrusted_peer_cannot_escalate_visibility(tmp_path):
    """An untrusted peer may SHRINK visibility (propagate a revoke) but never
    WIDEN it — no re-classifying a team-scoped memory as global.

    Lineage:
    main: introduced c3f6b6e2@db-schema-v15.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    src.store.register_agent("owner")
    m = src.add("scoped secret", owner="owner", visibility=["team:x"])
    b1 = tmp_path / "b1.jsonl"; export_bundle(src.store, b1)
    import_bundle(dst.store, str(b1), org_scope="full")  # dst now has it as team:x

    # Forge a bundle that escalates to global with a far-future ACL clock.
    forged = tmp_path / "forge.jsonl"
    _write_bundle(forged, {
        "kind": "memory", "id": m.id, "owner": "owner", "scope": "user",
        "type": "note", "content": "scoped secret", "summary": "", "tags": "[]",
        "visibility": "[\"global\"]", "source": "{}", "confidence": 0.8, "importance": 0.5,
        "created_at": m.created_at, "updated_at": m.updated_at,
        "acl_updated_at": _future(), "expires_at": None, "decay_policy": "exponential",
        "decay_half_life_days": 30.0, "last_accessed_at": None, "access_count": 0,
        "pinned": 0, "helpful_count": 0, "unhelpful_count": 0,
    })
    import_bundle(dst.store, str(forged), trusted=False, org_scope=None)
    vis = json.loads(_vis(dst, m.id))
    assert "global" not in vis and "team:x" in vis   # escalation refused


def test_first_seen_memory_cannot_seed_future_acl_clock(tmp_path):
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    memory = src.add("future ACL seed", owner="peer", visibility=["global"])
    exported = tmp_path / "exported.jsonl"
    export_bundle(src.store, exported)
    memory_entry = next(
        json.loads(line)
        for line in exported.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("kind") == "memory"
    )

    forged = tmp_path / "forged.jsonl"
    future_entry = dict(memory_entry, acl_updated_at="2100-01-01T00:00:00.000000Z")
    _write_bundle(forged, future_entry, version=4)
    rejected = import_bundle(dst.store, str(forged), org_scope="full")

    assert rejected["memories_skipped"] == 1
    assert dst.store.conn.execute(
        "SELECT 1 FROM memories WHERE id = ?", (memory.id,)
    ).fetchone() is None

    valid = tmp_path / "valid.jsonl"
    _write_bundle(valid, memory_entry, version=4)
    accepted = import_bundle(dst.store, str(valid), org_scope="full")

    assert accepted["memories_added"] == 1
    assert dst.get(memory.id).content == "future ACL seed"


def test_untrusted_peer_revoke_still_shrinks(tmp_path):
    """The legitimate case still works: an untrusted peer's SHRINK is applied.

    Lineage:
    main: introduced c3f6b6e2@db-schema-v15.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    src.store.register_agent("owner")
    m = src.add("s", owner="owner", visibility=["team:x", "global"])
    b1 = tmp_path / "b1.jsonl"; export_bundle(src.store, b1)
    import_bundle(dst.store, str(b1), org_scope="full")
    src.store.revoke_share(m.id, actor="owner", to_team="x")  # -> ["global"]
    b2 = tmp_path / "b2.jsonl"; export_bundle(src.store, b2)
    import_bundle(dst.store, str(b2), trusted=False, org_scope=None)
    assert set(json.loads(_vis(dst, m.id))) == {"global"}


def test_update_memory_visibility_propagates(tmp_path):
    """A visibility change made via update() bumps the ACL clock and propagates.

    Lineage:
    main: introduced c3f6b6e2@db-schema-v15.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    src.store.register_agent("o")
    m = src.add("x", owner="o", visibility=["global", "team:t"])
    b1 = tmp_path / "b1.jsonl"; export_bundle(src.store, b1)
    import_bundle(dst.store, str(b1), org_scope="full")
    src.store.update_memory(m.id, visibility=["team:t"])   # revoke global via update()
    b2 = tmp_path / "b2.jsonl"; export_bundle(src.store, b2)
    import_bundle(dst.store, str(b2), org_scope="full")
    assert set(json.loads(_vis(dst, m.id))) == {"team:t"}


def test_restore_archived_seeds_acl_clock(tmp_path):
    """A restored memory has a non-NULL acl clock (created_at floor), so it can't
    clobber a peer's newer revoke on the next sync.

    Lineage:
    main: introduced c3f6b6e2@db-schema-v15.
    """
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("o")
    m = c.add("temp", owner="o", visibility=["global"], expires_at="2000-01-01T00:00:00.000000Z")
    c.run_retention(decayed_half_lives=None)              # archive the expired memory
    c.restore_archived(m.id)
    acl = c.store.conn.execute(
        "SELECT acl_updated_at FROM memories WHERE id = ?", (m.id,)).fetchone()[0]
    assert acl == m.created_at


def test_sync_canonicalizes_basic_format_expiry_from_v3_peer(tmp_path):
    """Lineage:
    main: introduced 1287c647@db-schema-v20.
    time-helper: changed dc608742@db-schema-v21.
    time-helper: changed working-tree@db-schema-v22.
    direct sync-bundle binding: v3.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    memory = src.add(
        "Federated basic-format expiry sentinel.",
        owner="peer-agent",
        visibility=["global"],
    )
    current_bundle = tmp_path / "current.jsonl"
    export_bundle(src.store, current_bundle)
    current_lines = current_bundle.read_text(encoding="utf-8").splitlines()
    v3_record = json.loads(current_lines[1])
    v3_record["expires_at"] = "20990101T000000+00:00"
    bundle = tmp_path / "basic-expiry.jsonl"
    _write_bundle(bundle, v3_record, version=3)

    import_bundle(dst.store, str(bundle), org_scope="full")

    assert dst.get(memory.id).expires_at == "2099-01-01T00:00:00.000000Z"
    assert memory.id in {
        hit.record.id
        for hit in dst.search("federated basic format expiry sentinel")
    }


def test_sync_carries_canonical_expiry_from_v4_peer(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    direct sync-bundle binding: v4.
    """
    src = MemoryClient(home=tmp_path / "src")
    dst = MemoryClient(home=tmp_path / "dst")
    memory = src.add(
        "Federated canonical expiry sentinel.",
        owner="peer-agent",
        visibility=["global"],
        expires_at="2099-01-01T00:00:00.000000Z",
    )
    bundle = tmp_path / "canonical-expiry.jsonl"

    export_bundle(src.store, bundle)

    wire_lines = [
        json.loads(line)
        for line in bundle.read_text(encoding="utf-8").splitlines()
    ]
    assert wire_lines[0] == {"kind": "bundle", "version": 4}
    assert wire_lines[1]["expires_at"] == "2099-01-01T00:00:00.000000Z"

    import_bundle(dst.store, str(bundle), org_scope="full")

    assert dst.get(memory.id).expires_at == "2099-01-01T00:00:00.000000Z"
    assert memory.id in {
        hit.record.id
        for hit in dst.search("federated canonical expiry sentinel")
    }


# ---- web push leg is untrusted and cannot mutate org structure ----

def test_web_push_import_rejects_org_mutation(tmp_path):
    """Lineage:
    main: introduced bc2608c9@db-schema-v14.
    """
    from fastapi.testclient import TestClient

    from agent_memory_os.web_app import create_app

    c = MemoryClient(home=tmp_path)
    c.store.create_team("corp")
    app = create_app(home=tmp_path)  # no token → open, but still untrusted push
    client = TestClient(app)
    body = (json.dumps({"kind": "bundle", "version": 3}) + "\n"
            + json.dumps({"kind": "team", "id": "corp", "name": "corp",
                          "updated_at": _future(), "members": ["attacker"]}) + "\n")
    resp = client.post("/api/sync/import", content=body)
    assert resp.status_code == 200
    assert resp.json()["org_records_rejected"] == 1
    assert "attacker" not in c.store.get_team("corp")["members"]
