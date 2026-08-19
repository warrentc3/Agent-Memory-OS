"""First-class teams & projects (v0.13): membership, subset invariant, ACL,
cascade, and project-scoped sync."""

import tempfile

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app


def _fixture(tmp_path):
    c = MemoryClient(home=tmp_path)
    s = c.store
    for a in ("alice", "bob", "carol"):
        s.register_agent(a, kind="hermes")
    s.create_team("apollo", name="Apollo")
    for a in ("alice", "bob", "carol"):
        s.add_team_member("apollo", a)
    s.create_project("apollo-web", "apollo", name="Web")
    s.add_project_member("apollo-web", "alice")
    s.add_project_member("apollo-web", "bob")
    return c


def test_team_vs_project_visibility(tmp_path):
    c = _fixture(tmp_path)
    c.add("team-wide apollo", owner="alice", visibility=["team:apollo"])
    c.add("apollo-web only", owner="alice", visibility=["project:apollo-web"])

    def sees(agent, needle):
        return any(needle in h.record.content for h in c.search(needle, requester_agent_id=agent))

    assert sees("carol", "team-wide")            # team member sees team memory
    assert not sees("carol", "apollo-web only")  # NOT a project member
    assert sees("bob", "apollo-web only")        # project member
    c.store.register_agent("dave", kind="hermes")
    assert not sees("dave", "team-wide")         # not on the team


def test_project_member_must_be_team_member(tmp_path):
    c = _fixture(tmp_path)
    c.store.register_agent("stranger", kind="hermes")
    with pytest.raises(ValueError, match="must be a member of team"):
        c.store.add_project_member("apollo-web", "stranger")


def test_leaving_team_cascades_out_of_projects(tmp_path):
    c = _fixture(tmp_path)
    assert "alice" in c.store.get_project("apollo-web")["members"]
    c.store.remove_team_member("apollo", "alice")
    assert "alice" not in c.store.get_project("apollo-web")["members"]
    assert "alice" not in c.store.get_team("apollo")["members"]


def test_delete_team_cascades_projects(tmp_path):
    c = _fixture(tmp_path)
    assert c.store.delete_team("apollo") is True
    assert c.store.get_project("apollo-web") is None
    assert c.store.list_projects() == []


def test_removing_agent_clears_memberships(tmp_path):
    c = _fixture(tmp_path)
    c.store.remove_agent("bob")
    assert "bob" not in c.store.get_team("apollo")["members"]
    assert "bob" not in c.store.get_project("apollo-web")["members"]


def test_project_scoped_export_excludes_other_scopes(tmp_path):
    c = _fixture(tmp_path)
    c.add("team apollo memo", owner="alice", visibility=["team:apollo"])
    proj = c.add("apollo-web secret", owner="alice", visibility=["project:apollo-web"])
    c.add("alice private", owner="alice", visibility=[])
    bundle = tmp_path / "proj.jsonl"
    counts = c.export_bundle(bundle, project="apollo-web", include_private=False)
    assert counts["memories"] == 1
    import json
    mems = [json.loads(l) for l in bundle.read_text().splitlines() if '"memory"' in l]
    assert mems[0]["id"] == proj.id


def test_register_agent_reconciles_team_membership(tmp_path):
    """Declaring an agent's teams sets its membership (agents.toml behaviour)."""
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("neo", kind="hermes", teams=["apollo", "zeus"])
    assert set(c.store.teams_for("neo")) == {"apollo", "zeus"}
    # teams got auto-created
    assert {t["id"] for t in c.store.list_teams()} >= {"apollo", "zeus"}
    # re-declaring with fewer teams removes the dropped one
    c.store.register_agent("neo", kind="hermes", teams=["apollo"])
    assert c.store.teams_for("neo") == ["apollo"]


def test_migration_backfills_teams_from_agent_teams(tmp_path):
    """A DB created before migration 13 keeps its flat agent.teams as real
    team memberships after upgrade (simulated by register during this schema)."""
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("mizuki", kind="hermes", teams=["ops"])
    # membership resolves through the join table, and ACL honours it
    c.add("ops note", owner="x", visibility=["team:ops"])
    hits = c.search("ops note", requester_agent_id="mizuki")
    assert any("ops note" in h.record.content for h in hits)


def test_create_project_cannot_repoint_to_another_team(tmp_path):
    """Review R1: re-pointing a project at a different team would break the
    subset invariant — it must be rejected."""
    c = _fixture(tmp_path)
    c.store.create_team("zeus")
    with pytest.raises(ValueError, match="already exists under team"):
        c.store.create_project("apollo-web", "zeus")
    # unchanged
    assert c.store.get_project("apollo-web")["team_id"] == "apollo"


def test_register_agent_none_teams_preserves_membership(tmp_path):
    """Review R2: a metadata-only re-registration must not wipe memberships."""
    c = _fixture(tmp_path)
    assert set(c.store.teams_for("alice")) == {"apollo"}
    assert "alice" in c.store.get_project("apollo-web")["members"]
    # editing display name only (teams omitted / None)
    c.store.register_agent("alice", kind="hermes", display_name="Alice Renamed")
    assert set(c.store.teams_for("alice")) == {"apollo"}          # preserved
    assert "alice" in c.store.get_project("apollo-web")["members"]  # preserved
    # explicit empty list DOES clear
    c.store.register_agent("alice", kind="hermes", teams=[])
    assert c.store.teams_for("alice") == []


def test_web_agent_edit_without_teams_preserves_membership(tmp_path):
    web = TestClient(create_app(home=tmp_path))
    web.post("/api/agents", json={"id": "alice", "kind": "hermes"})
    web.post("/api/teams", json={"id": "apollo"})
    web.post("/api/teams/apollo/members", json={"agent_id": "alice"})
    # edit name, no teams field
    web.post("/api/agents", json={"id": "alice", "display_name": "A", "kind": "hermes"})
    assert web.get("/api/teams").json()["teams"][0]["members"] == ["alice"]


def test_deleting_scope_strips_grant_no_id_reuse_resurrection(tmp_path):
    """Review R5: deleting a team/project revokes its visibility grant so a
    reused id can't resurrect read access to the old scope's memory."""
    c = _fixture(tmp_path)
    m = c.add("acme team secret", owner="alice", visibility=["team:apollo"])
    c.store.delete_team("apollo")
    assert c.get(m.id).visibility == []  # grant stripped -> owner-private
    # recreate the id with a new member — must NOT see the old memory
    c.store.register_agent("mallory", kind="hermes")
    c.store.create_team("apollo")
    c.store.add_team_member("apollo", "mallory")
    assert not any("acme team secret" in h.record.content
                   for h in c.search("acme", requester_agent_id="mallory"))


def test_share_to_project_via_web(tmp_path):
    """Review R3: project sharing must be reachable via the web API."""
    web = TestClient(create_app(home=tmp_path))
    web.post("/api/agents", json={"id": "alice", "kind": "hermes"})
    web.post("/api/teams", json={"id": "apollo"})
    web.post("/api/teams/apollo/members", json={"agent_id": "alice"})
    web.post("/api/projects", json={"id": "web", "team_id": "apollo"})
    web.post("/api/projects/web/members", json={"agent_id": "alice"})
    mem = web.post("/api/memories", json={"content": "share target", "owner": "alice"}).json()
    r = web.post(f"/api/memories/{mem['id']}/share",
                 json={"actor": "alice", "to_project": "web"})
    assert r.status_code == 200
    assert r.json()["grant"] == "project:web"


def _sync(src, dst, tmp_path, name="b.jsonl"):
    b = tmp_path / name
    src.export_bundle(b, include_private=False)
    return dst.import_bundle(b, trusted=True)


def test_org_structure_syncs_and_converges(tmp_path):
    """G2: teams/projects/memberships federate; additions AND removals and
    deletions all converge across nodes."""
    A = MemoryClient(home=tmp_path / "a")
    B = MemoryClient(home=tmp_path / "b")
    for n in ("alice", "bob"):
        A.store.register_agent(n, kind="hermes")
    A.store.create_team("apollo")
    A.store.add_team_member("apollo", "alice")
    A.store.add_team_member("apollo", "bob")
    A.store.create_project("web", "apollo")
    A.store.add_project_member("web", "alice")

    _sync(A, B, tmp_path)
    assert B.store.get_team("apollo")["members"] == ["alice", "bob"]
    assert B.store.get_project("web")["members"] == ["alice"]

    # membership REMOVAL propagates (member-set replace on LWW)
    import time
    time.sleep(1.05)
    A.store.remove_team_member("apollo", "bob")
    _sync(A, B, tmp_path)
    assert B.store.get_team("apollo")["members"] == ["alice"]

    # deletions propagate via org tombstones
    time.sleep(1.05)
    A.store.delete_project("web")
    _sync(A, B, tmp_path)
    assert B.store.get_project("web") is None
    time.sleep(1.05)
    A.store.delete_team("apollo")
    _sync(A, B, tmp_path)
    assert B.store.get_team("apollo") is None


def test_synced_org_makes_project_acl_consistent_cross_node(tmp_path):
    """After org sync, a project:<id> memory synced to B resolves for the same
    member it did on A."""
    A = MemoryClient(home=tmp_path / "a")
    B = MemoryClient(home=tmp_path / "b")
    A.store.register_agent("alice", kind="hermes")
    A.store.create_team("apollo"); A.store.add_team_member("apollo", "alice")
    A.store.create_project("web", "apollo"); A.store.add_project_member("web", "alice")
    A.add("web project note", owner="alice", visibility=["project:web"])
    _sync(A, B, tmp_path)
    # B now has the project structure AND the memory; alice resolves it on B
    assert any("web project note" in h.record.content
               for h in B.search("web project note", requester_agent_id="alice"))


def test_org_tombstone_blocks_resurrection(tmp_path):
    """A deleted team can't be resurrected by an older team record in a bundle."""
    A = MemoryClient(home=tmp_path / "a")
    B = MemoryClient(home=tmp_path / "b")
    A.store.register_agent("alice", kind="hermes")
    A.store.create_team("apollo"); A.store.add_team_member("apollo", "alice")
    seed = tmp_path / "seed.jsonl"
    A.export_bundle(seed, include_private=False)  # bundle with the live team
    B.import_bundle(seed, trusted=True)
    assert B.store.get_team("apollo") is not None
    import time
    time.sleep(1.05)
    B.store.delete_team("apollo")                 # B deletes it (tombstone)
    B.import_bundle(seed, trusted=True)           # re-import the older live team
    assert B.store.get_team("apollo") is None     # tombstone wins


def test_membership_changes_are_audited(tmp_path):
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("alice", kind="hermes")
    c.store.create_team("apollo")
    c.store.add_team_member("apollo", "alice", actor="admin")
    actions = [a["action"] for a in c.org_audit_log()]
    assert "create_team" in actions and "add_team_member" in actions
    add = next(a for a in c.org_audit_log() if a["action"] == "add_team_member")
    assert add["actor"] == "admin" and "alice" in add["detail"]


def test_orphan_memory_detection_and_cleanup(tmp_path):
    """An orphan is reachable by NOBODY: its scope no longer exists AND its owner
    is not a live agent. A live owner or an existing (even empty) scope keeps a
    memory recoverable, so it must never be flagged — deleting it would be data
    loss (the v0.14-review data-loss fix)."""
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("alice", kind="hermes")
    c.store.create_team("apollo"); c.store.add_team_member("apollo", "alice")

    # (1) A truly orphaned memory: owner is not a registered agent and it is
    # scoped to a team this node does not have (e.g. synced in, then the team
    # was never created / was tombstoned).
    orphan = c.add("ghost team knowledge", owner="ext-node", visibility=["team:ghost"])
    # (2) NOT an orphan — a live owner can always read it, even scoped to a ghost team.
    owned = c.add("alice's note", owner="alice", visibility=["team:ghost"])
    # (3) NOT an orphan — global.
    g = c.add("global note", owner="alice", visibility=["global"])
    # (4) NOT an orphan — private memory of a live owner.
    p = c.add("private note", owner="alice", visibility=[])

    orphans = c.find_orphan_memories()
    assert [o["id"] for o in orphans] == [orphan.id]

    # Emptying an EXISTING team must NOT orphan its memories (recoverable by
    # re-adding a member; owner also still reads them).
    tm = c.add("apollo team note", owner="ext-node", visibility=["team:apollo"])
    c.store.remove_team_member("apollo", "alice")     # apollo now empty but EXISTS
    assert tm.id not in {o["id"] for o in c.find_orphan_memories()}

    assert c.delete_orphan_memories() == {"orphans_deleted": 1}
    assert c.get(orphan.id) is None
    for keep in (owned, g, p, tm):
        assert c.get(keep.id) is not None             # all untouched


def test_maintenance_scan_and_vacuum(tmp_path):
    c = MemoryClient(home=tmp_path)
    c.add("x", visibility=["global"])
    scan = c.maintenance_scan()
    assert set(scan) >= {"orphan_memories", "memories", "indexed", "teams", "projects"}
    vac = c.vacuum()
    assert "bytes_reclaimed" in vac


def test_update_command_detects_deployment(monkeypatch, capsys):
    from agent_memory_os import cli
    monkeypatch.setattr(cli, "_pypi_latest", lambda pkg: "999.0.0")
    rc = cli.main(["update", "--check"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "latest:" in out and "999.0.0" in out and "deployment:" in out


def test_teams_projects_api(tmp_path):
    web = TestClient(create_app(home=tmp_path))
    for a in ("alice", "bob"):
        web.post("/api/agents", json={"id": a, "kind": "hermes"})
    assert web.post("/api/teams", json={"id": "apollo", "name": "Apollo"}).status_code == 200
    web.post("/api/teams/apollo/members", json={"agent_id": "alice"})
    web.post("/api/teams/apollo/members", json={"agent_id": "bob"})
    assert web.post("/api/projects", json={"id": "web", "team_id": "apollo"}).status_code == 200
    web.post("/api/projects/web/members", json={"agent_id": "alice"})
    # subset enforced through the API
    r = web.post("/api/projects/web/members", json={"agent_id": "stranger"})
    assert r.status_code == 400
    team = web.get("/api/teams").json()["teams"][0]
    assert set(team["members"]) == {"alice", "bob"}
    proj = web.get("/api/projects?team=apollo").json()["projects"][0]
    assert proj["members"] == ["alice"]


# ---------- team rename (v1.8.3) ----------

def test_team_rename_moves_every_reference_the_id_carries(tmp_path):
    """A team id is not just a row key: it is the token inside every
    `team:<id>` grant, the parent key of its projects, and the `source.team_id`
    the legacy bare `team` grant resolves through. Renaming must move all of
    them atomically or the id's memory becomes unreachable."""
    c = _fixture(tmp_path)
    s = c.store
    team_mem = c.add("team scoped", owner="alice", visibility=["team:apollo"])
    proj_mem = c.add("project scoped", owner="alice", visibility=["project:apollo-web"])
    bare = c.add("bare grant", owner="alice", visibility=["team"],
                 source={"team_id": "apollo"})

    created_before = s.get_team("apollo")["created_at"]
    pre = s.team_rename_preview("apollo", "artemis")
    assert pre["exists"] and not pre["target_exists"]
    assert pre["members"] == 3
    assert pre["projects"] == ["apollo-web"]
    assert pre["explicit_grants"] == 1
    assert pre["bare_grants"] == 1

    counts = c.rename_team("apollo", "artemis")
    assert counts["members"] == 3
    assert counts["projects"] == 1
    assert counts["explicit_grants"] == 1
    assert counts["bare_grants"] == 1

    assert s.get_team("apollo") is None
    team = s.get_team("artemis")
    assert team["members"] == ["alice", "bob", "carol"]
    assert team["projects"] == ["apollo-web"]
    # created_at is carried over: a rename is not a re-creation.
    assert team["created_at"] == created_before
    # Every scope still resolves for a member — the real regression risk.
    assert c.get_visible(team_mem.id, requester_agent_id="bob") is not None
    assert c.get_visible(proj_mem.id, requester_agent_id="bob") is not None
    assert c.get_visible(bare.id, requester_agent_id="bob") is not None
    # ...and still does NOT resolve for a non-member.
    s.register_agent("dave", kind="hermes")
    assert c.get_visible(team_mem.id, requester_agent_id="dave") is None
    c.close()


def test_team_rename_bumps_the_acl_clock_not_the_content_clock(tmp_path):
    """Sync converges visibility on `acl_updated_at`. A rename that left it
    alone would lose the new grant to a peer's older copy; bumping the content
    clock instead would falsely mark the memory as edited."""
    c = _fixture(tmp_path)
    m = c.add("team scoped", owner="alice", visibility=["team:apollo"])
    before = c.store.conn.execute(
        "SELECT updated_at, acl_updated_at FROM memories WHERE id = ?", (m.id,)).fetchone()
    c.rename_team("apollo", "artemis")
    after = c.store.conn.execute(
        "SELECT updated_at, acl_updated_at FROM memories WHERE id = ?", (m.id,)).fetchone()
    assert after["updated_at"] == before["updated_at"]
    assert after["acl_updated_at"] >= before["acl_updated_at"]
    c.close()


def test_team_rename_refuses_to_merge_or_invent(tmp_path):
    c = _fixture(tmp_path)
    c.store.create_team("artemis", name="Artemis")
    with pytest.raises(ValueError, match="already exists"):
        c.rename_team("apollo", "artemis")
    with pytest.raises(KeyError):
        c.rename_team("nosuch", "whatever")
    with pytest.raises(ValueError, match="identical"):
        c.rename_team("apollo", "apollo")
    with pytest.raises(ValueError):
        c.rename_team("apollo", "   ")
    # the failed attempts changed nothing
    assert c.store.get_team("apollo") is not None
    c.close()


def test_team_rename_display_name_policy(tmp_path):
    """A name that merely mirrored the id follows the rename; a name the
    operator actually chose is preserved; an explicit name always wins."""
    c = MemoryClient(home=tmp_path)
    s = c.store
    s.create_team("mirror", name="mirror")
    s.create_team("labelled", name="Real Label")
    assert c.rename_team("mirror", "renamed")["name"] == "renamed"
    assert c.rename_team("labelled", "relabelled")["name"] == "Real Label"
    s.create_team("explicit", name="explicit")
    assert c.rename_team("explicit", "third", name="Chosen")["name"] == "Chosen"
    c.close()


def test_team_rename_does_not_tombstone_the_old_id(tmp_path):
    """Applying a team tombstone cascade-deletes that team's projects and
    strips their `project:<id>` grants from memories — damage the renamed
    records cannot undo. A rename must therefore never emit one, and must warn
    when peers exist instead."""
    c = _fixture(tmp_path)
    c.rename_team("apollo", "artemis")
    assert not [t for t in c.store.list_org_tombstones() if t[1] == "apollo"]
    c.store.add_peer("http://peer:8000", policy="shared")
    c.store.create_team("second", name="second")
    result = c.rename_team("second", "third")
    assert "sync_warning" in result and "http://peer:8000" in result["sync_warning"]
    c.close()


def test_team_rename_is_audited(tmp_path):
    c = _fixture(tmp_path)
    c.rename_team("apollo", "artemis", actor="operator")
    entry = [r for r in c.store.org_audit_log(limit=10) if r["action"] == "rename_team"]
    assert entry and entry[0]["detail"] == "apollo -> artemis"
    assert entry[0]["actor"] == "operator"
    # History is never rewritten: the pre-rename entries still name the old id.
    assert any("apollo" in r["detail"] for r in c.store.org_audit_log(limit=50)
               if r["action"] == "create_team")
    c.close()


def test_team_rename_api(tmp_path):
    c = _fixture(tmp_path)
    c.add("team scoped", owner="alice", visibility=["team:apollo"])
    c.close()
    app = create_app(home=tmp_path, token=None)
    tc = TestClient(app)
    pre = tc.get("/api/teams/apollo/rename-preview", params={"new_id": "artemis"})
    assert pre.status_code == 200
    assert pre.json()["explicit_grants"] == 1
    assert pre.json()["projects"] == ["apollo-web"]
    r = tc.post("/api/teams/apollo/rename", json={"new_id": "artemis"})
    assert r.status_code == 200 and r.json()["members"] == 3
    assert [t["id"] for t in tc.get("/api/teams").json()["teams"]] == ["artemis"]
    assert tc.post("/api/teams/nosuch/rename", json={"new_id": "x"}).status_code == 404
    tc.post("/api/teams", json={"id": "taken", "name": "taken"})
    assert tc.post("/api/teams/artemis/rename", json={"new_id": "taken"}).status_code == 400


def _mirror(store, agent_id):
    import json as _json
    row = store.conn.execute("SELECT teams FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return sorted(_json.loads(row[0] or "[]")) if row else None


def test_agents_teams_mirror_tracks_every_membership_path(tmp_path):
    """`agents.teams` mirrors team_members. A stale mirror is a trap rather
    than cosmetic: `register_agent` reconciles membership to the list it is
    handed and drops any team absent from it, and the console's agent editor
    round-trips exactly this column — so a mirror left behind by any one
    mutation path would move an agent back to a team that may not exist,
    taking its project memberships with it."""
    c = _fixture(tmp_path)
    s = c.store
    s.create_team("unrelated", name="unrelated")
    s.add_team_member("unrelated", "alice")
    assert _mirror(s, "alice") == ["apollo", "unrelated"]      # add_team_member
    s.remove_team_member("unrelated", "alice")
    assert _mirror(s, "alice") == ["apollo"]                   # remove_team_member
    c.rename_team("apollo", "artemis")
    assert _mirror(s, "alice") == ["artemis"]                  # rename_team
    s.create_team("doomed"); s.add_team_member("doomed", "alice")
    s.delete_team("doomed")
    assert _mirror(s, "alice") == ["artemis"]                  # delete_team
    # Round-tripping the mirror is now a no-op rather than a regression.
    s.register_agent("alice", kind="hermes", teams=_mirror(s, "alice"))
    assert s.teams_for("alice") == ["artemis"]
    assert "alice" in s.get_project("apollo-web")["members"]
    c.close()


def test_reassign_owner_keeps_the_mirror_with_the_surviving_identity(tmp_path):
    c = _fixture(tmp_path)
    s = c.store
    s.reassign_owner("carol", "carol-2")
    assert _mirror(s, "carol-2") == ["apollo"]
    assert s.conn.execute("SELECT COUNT(*) FROM agents WHERE id='carol'").fetchone()[0] == 0
    c.close()


def test_agy_is_a_registrable_agent_kind(tmp_path):
    """Antigravity (CLI and IDE) is a first-class integration, so it gets its
    own kind rather than hiding under `custom`."""
    c = MemoryClient(home=tmp_path)
    assert "agy" in c.store.AGENT_KINDS
    c.store.register_agent("agy-cli", display_name="Antigravity CLI", kind="agy")
    assert c.store.get_agent("agy-cli")["kind"] == "agy"
    with pytest.raises(ValueError, match="kind must be one of"):
        c.store.register_agent("nope", kind="not-a-kind")
    c.close()
