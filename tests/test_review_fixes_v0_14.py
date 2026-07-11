"""Regression tests for the v0.14 code+security review findings.

Each test pins one fixed vulnerability/bug so it cannot silently return. See
docs/reviews/20260712-v0.14.0-review.md for the findings these map to.
"""

from __future__ import annotations

import json

from agent_memory_os import MemoryClient
from agent_memory_os.schema import utc_now
from agent_memory_os.sync import export_bundle, import_bundle


def _write_bundle(path, *entries, version=3):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "bundle", "version": version}) + "\n")
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _future():  # a timestamp far enough ahead to (previously) win LWW forever
    return "9999-12-31T23:59:59+00:00"


def _now():  # a legitimate, not-rejected current timestamp
    return utc_now()


# ---- H1: org merges must honour the peer's trust scope ----

def test_untrusted_push_cannot_forge_membership(tmp_path):
    """org_scope=None (an anonymous push / 'shared' peer) applies NO org records."""
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
    """A 'team:alpha' peer may assert team alpha but not team beta."""
    c = MemoryClient(home=tmp_path)
    c.store.create_team("alpha"); c.store.create_team("beta")
    # Bump both so the incoming records win LWW on merit, not on being newer.
    ts = _now()
    c.store.conn.execute("UPDATE teams SET updated_at = ? WHERE id IN ('alpha','beta')",
                         ("2020-01-01T00:00:00+00:00",))
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
    SAME member set, not each keep its own."""
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
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("a1"); c.store.create_team("secret")
    c.store.add_team_member("secret", "a1")
    out = tmp_path / "shared.jsonl"
    export_bundle(c.store, out, include_private=False, include_org=False)
    kinds = {json.loads(line)["kind"] for line in out.read_text().splitlines()}
    assert "team" not in kinds and "project" not in kinds and "org_tombstone" not in kinds


# ---- M3: project-scoped export narrows the parent-team roster ----

def test_project_export_does_not_leak_team_roster(tmp_path):
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


# ---- M5: deleting a team strips the bare-`team` grant (id-reuse can't resurrect) ----

def test_delete_team_strips_bare_team_grant(tmp_path):
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("alice")
    c.store.create_team("X"); c.store.add_team_member("X", "alice")
    # A memory using the legacy bare-`team` scheme keyed by source.team_id.
    m = c.add("team secret", owner="ext", visibility=["team"], source={"team_id": "X"})
    c.store.delete_team("X")
    vis = json.loads(c.store.conn.execute(
        "SELECT visibility FROM memories WHERE id = ?", (m.id,)).fetchone()[0])
    assert "team" not in vis  # bare grant stripped; a reused id X can't resurrect access


# ---- web push leg is untrusted and cannot mutate org structure ----

def test_web_push_import_rejects_org_mutation(tmp_path):
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
