"""/healthz + /metrics observability endpoints (Phase C)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app


def _client(tmp_path, token=None):
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("a1")
    c.add("hello world", owner="a1", visibility=["global"])
    return TestClient(create_app(home=tmp_path, token=token))


def test_healthz_unauthenticated_ok(tmp_path):
    # Even with a token set, /healthz is outside /api/ and needs no auth.
    """Lineage:
    main: introduced 5ec91d84@db-schema-v15.
    """
    client = _client(tmp_path, token="secret")
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["integrity"] is True


def test_metrics_prometheus_format_unauthenticated(tmp_path):
    """Lineage:
    main: introduced 5ec91d84@db-schema-v15.
    """
    client = _client(tmp_path, token="secret")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    text = r.text
    assert "agentmemory_memories_total 1" in text
    assert "# TYPE agentmemory_orphan_memories gauge" in text
    assert "agentmemory_index_drift" in text
    assert "agentmemory_integrity_ok 1" in text


def test_metrics_reflects_counts(tmp_path):
    """Lineage:
    main: introduced 5ec91d84@db-schema-v15.
    """
    c = MemoryClient(home=tmp_path)
    c.store.register_agent("a1")
    c.store.create_team("t1"); c.store.create_team("t2")
    app = create_app(home=tmp_path)
    r = TestClient(app).get("/metrics")
    assert "agentmemory_teams_total 2" in r.text
