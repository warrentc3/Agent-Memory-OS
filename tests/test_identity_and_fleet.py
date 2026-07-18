"""v1.4 identity & fleet ops: rename propagation, node identity, PATH, team update."""

from __future__ import annotations

import json
import os

import pytest

from agent_memory_os.client import MemoryClient


def test_default_node_name_differs_per_account(tmp_path, monkeypatch):
    """Two accounts using the default home must not get the same node name."""
    import getpass

    from agent_memory_os.settings import default_node_name

    monkeypatch.setattr(getpass, "getuser", lambda: "alice")
    a = default_node_name(tmp_path / ".agent-memory")
    monkeypatch.setattr(getpass, "getuser", lambda: "bob")
    b = default_node_name(tmp_path / ".agent-memory")
    assert a != b and "alice" in a and "bob" in b


def test_rename_agent_migrates_everything(tmp_path):
    client = MemoryClient(home=tmp_path)
    s = client.store
    s.register_agent("old-bot", display_name="Old", kind="custom")
    s.create_team("apollo")
    s.add_team_member("apollo", "old-bot")
    s.create_project("web", team_id="apollo")
    s.add_project_member("web", "old-bot")
    owned = client.add("private note", owner="old-bot", visibility=[])
    granted = client.add("shared with old-bot", owner="someone",
                         visibility=["agent:old-bot"])
    from agent_memory_os.schema import RecallProfile
    client.save_profile(RecallProfile(agent_id="old-bot", type_weights={"note": 1.2}))

    counts = s.rename_agent("old-bot", "new-bot")
    assert counts["memories_owner"] == 1
    assert counts["visibility_grants"] == 1
    assert counts["agents_registry"] == 1
    assert counts["team_memberships"] == 1
    assert counts["project_memberships"] == 1
    assert counts["recall_profiles"] == 1

    # New identity fully works; old one is gone everywhere.
    assert client.get(owned.id).owner == "new-bot"
    assert client.get(granted.id).visibility == ["agent:new-bot"]
    assert "new-bot" in (s.get_team("apollo").get("members") or [])
    assert "old-bot" not in (s.get_team("apollo").get("members") or [])
    hits = client.search("shared", requester_agent_id="new-bot")
    assert any("old-bot" in h.record.content for h in hits)
    # errors: unknown -> zero counts is fine, but collision is refused
    s.register_agent("other", kind="custom")
    with pytest.raises(ValueError, match="already exists"):
        s.rename_agent("new-bot", "other")
    client.close()


def test_update_peer_name(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.add_peer("http://127.0.0.1:9001", policy="shared", name="old-name")
    assert client.store.update_peer_name("http://127.0.0.1:9001", "renamed-node") is True
    assert client.store.list_peers()[0]["name"] == "renamed-node"
    assert client.store.update_peer_name("http://127.0.0.1:9001", "renamed-node") is False
    client.close()


@pytest.fixture()
def web(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient as HttpClient

    from agent_memory_os.web_app import create_app

    app = create_app(tmp_path)
    with HttpClient(app) as http:
        yield {"http": http, "home": tmp_path}


def test_node_rename_api_and_healthz_version(web):
    http = web["http"]
    health = http.get("/healthz").json()
    assert health.get("version")  # team update needs cross-node versions

    r = http.post("/api/node", json={"node_name": "renamed-via-api"})
    assert r.status_code == 200 and r.json()["node_name"] == "renamed-via-api"
    # persisted AND applied to the running app
    assert http.get("/healthz").json()["node"] == "renamed-via-api"
    from agent_memory_os.settings import load_instance_settings
    assert load_instance_settings(web["home"]).node_name == "renamed-via-api"


def test_agents_registry_is_seeded_for_first_run(web):
    agents = web["http"].get("/api/agents").json()["agents"]
    assert agents, "member picker must have at least the node's own agent"


def test_agent_rename_api(web):
    http = web["http"]
    http.post("/api/agents", json={"id": "bot-a", "kind": "custom"})
    r = http.post("/api/agents/rename", json={"old_id": "bot-a", "new_id": "bot-b"})
    assert r.status_code == 200 and r.json()["changed"]["agents_registry"] == 1
    assert http.post("/api/agents/rename",
                     json={"old_id": "ghost", "new_id": "bot-b"}).status_code == 400


def test_team_update_authorization_gate(tmp_path, monkeypatch):
    """Sync token may hit update-run ONLY with the operator opt-in."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient as HttpClient

    from agent_memory_os import tokens
    from agent_memory_os.web_app import create_app

    tokens.create_token(tmp_path)
    sync_token = tokens.create_token(tmp_path, tier="sync")
    headers = {"Authorization": f"Bearer {sync_token}"}

    monkeypatch.delenv("AGENT_MEMORY_ALLOW_TEAM_UPDATE", raising=False)
    with HttpClient(create_app(tmp_path)) as http:
        r = http.post("/api/maintenance/update-run?confirm=update", headers=headers)
        assert r.status_code == 403  # not opted in

    monkeypatch.setenv("AGENT_MEMORY_ALLOW_TEAM_UPDATE", "1")
    with HttpClient(create_app(tmp_path)) as http:
        r = http.post("/api/maintenance/update-run?confirm=update", headers=headers)
        assert r.status_code != 403  # authorized (may 400 in docker-less test env)
        # and the opt-in does NOT widen anything else for the sync tier
        assert http.get("/api/memories", headers=headers).status_code in (401, 403)


def test_path_show_and_install(tmp_path, monkeypatch, capsys):
    from agent_memory_os import cli

    monkeypatch.setattr(cli, "_scripts_dir", lambda: "/nonexistent/scripts-dir")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = cli.main(["path", "show"])
    assert rc == 1 and "NO" in capsys.readouterr().out

    rc = cli.main(["path", "install"])
    assert rc == 0
    out = capsys.readouterr().out
    zshrc = tmp_path / ".zshrc"
    assert zshrc.exists() and "/nonexistent/scripts-dir" in zshrc.read_text()
    # idempotent
    cli.main(["path", "install"])
    assert zshrc.read_text().count("/nonexistent/scripts-dir") == 1


def test_redeemed_by_records_the_actual_agent(tmp_path, monkeypatch):
    """The audit column stores the joiner's agent id, not a 'pending' stub."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient as HttpClient

    from agent_memory_os import pairing
    from agent_memory_os.web_app import create_app

    home = tmp_path / "inv"
    app = create_app(home)
    with HttpClient(app) as http:
        c = MemoryClient(home=home)
        c.store.create_team("apollo")
        invite = pairing.issue_invite(c, "apollo")

        def bridge(url, body, *, timeout=15):
            r = http.post(pairing.REDEEM_PATH, json=body)
            assert r.status_code == 200, r.text
            return r.json()

        monkeypatch.setattr(pairing, "_post_redeem", bridge)
        j = MemoryClient(home=tmp_path / "joiner")
        pairing.join_with_code(j, invite["code"], "http://127.0.0.1:9",
                               agent_id="account-z", home=str(tmp_path / "joiner"))
        row = c.store.conn.execute(
            "SELECT redeemed_by FROM pairing_invites").fetchone()
        assert row["redeemed_by"] == "account-z"
        c.close(); j.close()


def test_path_install_replaces_stale_line(tmp_path, monkeypatch, capsys):
    from agent_memory_os import cli

    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("HOME", str(tmp_path))
    zshrc = tmp_path / ".zshrc"

    monkeypatch.setattr(cli, "_scripts_dir", lambda: "/old/py3.11/bin")
    cli.main(["path", "install"])
    monkeypatch.setattr(cli, "_scripts_dir", lambda: "/new/py3.12/bin")
    cli.main(["path", "install"])

    text = zshrc.read_text()
    assert "/new/py3.12/bin" in text
    assert "/old/py3.11/bin" not in text  # stale entry removed, not accumulated
    assert text.count("added by agent-memory") == 1
