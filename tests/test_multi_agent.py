"""Multi-agent collaboration: one project mixing Claude Code, Codex, OpenClaw,
and multiple Hermes profiles against one store, with shared project memory."""

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app


def test_agent_registry_crud_and_validation(tmp_path):
    """Lineage:
    main: introduced 4436ea6d@db-schema-v8.
    """
    client = MemoryClient(home=tmp_path)

    with pytest.raises(ValueError):
        client.register_agent("x", kind="wizard")
    with pytest.raises(ValueError):
        client.register_agent("  ")

    client.register_agent("neo", display_name="Neo", kind="claude-code", teams=["apollo"])
    client.register_agent("codex-1", kind="codex", teams=["apollo", "zeus"])
    agents = client.list_agents()
    assert [agent["id"] for agent in agents] == ["codex-1", "neo"]
    assert agents[1]["teams"] == ["apollo"]

    # re-register updates in place
    client.register_agent("neo", kind="claude-code", teams=["apollo", "zeus"])
    assert client.store.get_agent("neo")["teams"] == ["apollo", "zeus"]

    assert client.remove_agent("codex-1") is True
    assert client.remove_agent("codex-1") is False


def test_project_memory_visible_to_registered_team_members(tmp_path):
    """The core scenario: a mixed fleet shares project memory via one team.

    Lineage:
    main: introduced 4436ea6d@db-schema-v8.
    """
    client = MemoryClient(home=tmp_path)
    fleet = {
        "cc-main": "claude-code",
        "codex-1": "codex",
        "claw-1": "openclaw",
        "hermes-neo": "hermes",
        "hermes-mizuki": "hermes",
    }
    for agent_id, kind in fleet.items():
        client.register_agent(agent_id, kind=kind, teams=["apollo"])
    client.register_agent("outsider", kind="custom", teams=["other-project"])

    project_memory = client.add(
        "Apollo project uses port 8000 for staging deploys.",
        owner="hermes-neo", scope="project", visibility=["team:apollo"],
    )
    private = client.add(
        "hermes-mizuki private reflection.", owner="hermes-mizuki", visibility=[],
    )

    # every fleet member sees the project memory WITHOUT wiring team ids
    for agent_id in fleet:
        hits = client.search("apollo staging port", requester_agent_id=agent_id)
        assert project_memory.id in {hit.record.id for hit in hits}, agent_id

    # outsiders and other teams do not
    assert client.search("apollo staging port", requester_agent_id="outsider") == []
    # private memories stay private inside the fleet
    hits = client.search("private reflection", requester_agent_id="hermes-neo")
    assert private.id not in {hit.record.id for hit in hits}

    # membership changes apply immediately (team cache invalidation)
    client.register_agent("codex-1", kind="codex", teams=[])
    assert client.search("apollo staging port", requester_agent_id="codex-1") == []


def test_team_memory_flows_through_pack_and_orchestrator(tmp_path):
    """Lineage:
    main: introduced 4436ea6d@db-schema-v8.
    """
    client = MemoryClient(home=tmp_path)
    client.register_agent("claw-1", kind="openclaw", teams=["apollo"])
    client.add(
        "Apollo deploy checklist: run smoke tests first.",
        owner="cc-main", scope="project", type="procedure", visibility=["team:apollo"],
    )

    pack = client.context_pack("apollo deploy", requester_agent_id="claw-1")
    assert "smoke tests" in pack

    orchestrated = client.orchestrate_context("apollo deploy", requester_agent_id="claw-1")
    assert "smoke tests" in orchestrated.text


def test_web_api_agents_endpoints(tmp_path):
    """Lineage:
    main: introduced 4436ea6d@db-schema-v8; f3b6a55f@db-schema-v16.
    """
    web = TestClient(create_app(home=tmp_path))

    saved = web.post("/api/agents", json={
        "id": "neo", "display_name": "Neo", "kind": "claude-code", "teams": ["apollo"],
    })
    assert saved.status_code == 200 and saved.json()["teams"] == ["apollo"]
    assert web.post("/api/agents", json={"id": "x", "kind": "wizard"}).status_code == 400

    web.post("/api/memories", json={"content": "Neo memory.", "owner": "neo", "visibility": []})
    listed = web.get("/api/agents").json()["agents"]
    # The registry also contains the auto-seeded node-default agent, so look
    # neo up by id rather than by position.
    neo = next(a for a in listed if a["id"] == "neo")
    assert neo["memory_count"] == 1

    assert web.delete("/api/agents/neo").status_code == 200
    assert web.delete("/api/agents/neo").status_code == 404


def test_team_scoped_bundle_export(tmp_path):
    """Lineage:
    main: introduced 4436ea6d@db-schema-v8; 06cb42f7@db-schema-v9.
    """
    host = MemoryClient(home=tmp_path / "src")
    host.register_agent("neo", kind="hermes", teams=["apollo"])
    host.register_agent("stranger", kind="custom", teams=["zeus"])
    from agent_memory_os import RecallProfile
    host.save_profile(RecallProfile(agent_id="neo", type_weights={"procedure": 1.5}))
    host.save_profile(RecallProfile(agent_id="stranger", type_weights={"note": 1.2}))

    in_team_a = host.add("Apollo shared fact one.", visibility=["team:apollo"])
    in_team_b = host.add("Apollo shared fact two.", visibility=["team:apollo"])
    outside = host.add("Zeus secret.", visibility=["team:zeus"])
    host.link(in_team_a.id, in_team_b.id, weight=0.8)
    host.link(in_team_a.id, outside.id, weight=0.9)  # crosses the boundary

    bundle = tmp_path / "apollo.jsonl"
    counts = host.export_bundle(bundle, team="apollo")
    assert counts == {"memories": 2, "links": 1, "profiles": 1, "tombstones": 0}

    target = MemoryClient(home=tmp_path / "dst")
    stats = target.import_bundle(bundle)
    assert stats["memories_added"] == 2
    assert target.get(outside.id) is None                 # boundary held
    assert target.get(in_team_a.id) is not None
    assert target.load_profile("neo") is not None
    assert target.load_profile("stranger") is None
    host.close(); target.close()
