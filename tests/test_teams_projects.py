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
