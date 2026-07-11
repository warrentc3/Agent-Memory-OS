"""Phase E backend: usage cards, update endpoints, read-only token tier."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app


def _seed(tmp_path):
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("alice"); c.store.register_agent("bob")
    c.store.create_team("eng"); c.store.add_team_member("eng", "alice")
    c.store.create_project("proj", "eng"); c.store.add_project_member("proj", "alice")
    c.add("alice global memory content here", owner="alice", visibility=["global"])
    c.add("team scoped knowledge", owner="alice", visibility=["team:eng"])
    c.add("project note", owner="bob", visibility=["project:proj"])
    return c


def test_usage_summary_four_cards(tmp_path):
    _seed(tmp_path)
    r = TestClient(create_app(home=tmp_path)).get("/api/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["memories"] == 3
    assert body["total"]["tokens"] > 0
    agents = {a["id"] for a in body["by_agent"]}
    assert {"alice", "bob"} <= agents
    assert any(t["id"] == "eng" for t in body["by_team"])
    assert any(p["id"] == "proj" for p in body["by_project"])


def test_update_check_shape(tmp_path):
    _seed(tmp_path)
    r = TestClient(create_app(home=tmp_path)).get("/api/maintenance/update-check")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"current", "latest", "update_available", "deployment"}
    assert body["deployment"] in ("host", "docker")


def test_update_run_requires_confirm(tmp_path):
    _seed(tmp_path)
    client = TestClient(create_app(home=tmp_path))
    assert client.post("/api/maintenance/update-run").status_code == 400


def test_readonly_token_allows_get_blocks_mutation(tmp_path):
    _seed(tmp_path)
    app = create_app(home=tmp_path, token="FULL", readonly_token="RO")
    client = TestClient(app)
    ro = {"Authorization": "Bearer RO"}
    full = {"Authorization": "Bearer FULL"}

    # read-only token: GET ok
    assert client.get("/api/usage", headers=ro).status_code == 200
    assert client.get("/api/stats", headers=ro).status_code == 200
    # read-only token: mutation forbidden (403)
    assert client.post("/api/maintenance/vacuum", headers=ro).status_code == 403
    # full token: mutation ok
    assert client.post("/api/maintenance/vacuum", headers=full).status_code == 200
    # no token: unauthorized
    assert client.get("/api/usage").status_code == 401


def test_page_shell_has_new_ui_elements(tmp_path):
    """The served HTML shell includes the Phase-E additions."""
    _seed(tmp_path)
    html = TestClient(create_app(home=tmp_path)).get("/").text
    for marker in ('id="version-badge"', 'id="usage-cards"', 'id="btn-maint-update"',
                   'id="audit-list"', 'id="graph-filter"', "loadVersionBadge",
                   "Token 用量"):  # zh-TW i18n injected
        assert marker in html, marker


def test_readonly_token_file_autoloads(tmp_path):
    from agent_memory_os import tokens

    _seed(tmp_path)
    tokens.create_token(tmp_path)                     # full
    ro = tokens.create_token(tmp_path, readonly=True)  # read-only
    app = create_app(home=tmp_path)                    # both auto-loaded from files
    client = TestClient(app)
    assert client.get("/api/usage", headers={"Authorization": f"Bearer {ro}"}).status_code == 200
    assert client.post("/api/maintenance/vacuum",
                       headers={"Authorization": f"Bearer {ro}"}).status_code == 403
