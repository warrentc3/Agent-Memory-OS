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
