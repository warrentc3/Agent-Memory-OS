"""Per-instance settings: node name + Web UI port (multiple instances on one host)."""

import socket

from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os import settings as st
from agent_memory_os.web_app import create_app


def test_default_node_name_disambiguates_by_home(tmp_path):
    a = st.default_node_name(tmp_path / "alpha")
    b = st.default_node_name(tmp_path / "beta")
    assert a != b
    assert a.endswith("-alpha") and b.endswith("-beta")


def test_settings_roundtrip_and_update(tmp_path):
    s = st.load_instance_settings(tmp_path)          # defaults
    assert s.port == 8000 and s.host == "127.0.0.1"
    st.update_instance_settings(tmp_path, node_name="mizuki-laptop", port=8123)
    reloaded = st.load_instance_settings(tmp_path)
    assert reloaded.node_name == "mizuki-laptop"
    assert reloaded.port == 8123
    # updating one field keeps the others
    st.update_instance_settings(tmp_path, host="0.0.0.0")
    again = st.load_instance_settings(tmp_path)
    assert again.host == "0.0.0.0" and again.node_name == "mizuki-laptop" and again.port == 8123


def test_client_exposes_node_name_from_settings(tmp_path):
    st.update_instance_settings(tmp_path, node_name="node-A")
    client = MemoryClient(home=tmp_path)
    assert client.node_name == "node-A"


def test_find_available_port_skips_taken(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        chosen = st.find_available_port("127.0.0.1", busy_port)
        assert chosen != busy_port
        assert st.port_is_free("127.0.0.1", chosen)


def test_api_node_reports_name(tmp_path):
    st.update_instance_settings(tmp_path, node_name="apollo-hub")
    web = TestClient(create_app(home=tmp_path))
    res = web.get("/api/node")
    assert res.status_code == 200
    assert res.json()["node_name"] == "apollo-hub"


def test_peer_stores_and_lists_name(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.add_peer("http://peer:8000", policy="shared", name="codex-box")
    peer = client.store.list_peers()[0]
    assert peer["name"] == "codex-box"
    # renaming
    assert client.store.set_peer_name("http://peer:8000", "codex-renamed")
    assert client.store.list_peers()[0]["name"] == "codex-renamed"


def test_bundle_header_carries_node_name(tmp_path):
    st.update_instance_settings(tmp_path, node_name="origin-node")
    client = MemoryClient(home=tmp_path)
    client.add("shared thing", visibility=["global"])
    bundle = tmp_path / "b.jsonl"
    client.export_bundle(bundle, include_private=False)
    import json
    header = json.loads(bundle.read_text(encoding="utf-8").splitlines()[0])
    assert header["node_name"] == "origin-node"


def test_add_peer_auto_fetches_node_name(tmp_path, monkeypatch):
    """POST /api/peers with no name pulls the peer's advertised node_name."""
    st.update_instance_settings(tmp_path / "peer", node_name="the-peer")
    peer_app = TestClient(create_app(home=tmp_path / "peer"))

    from agent_memory_os import sync as sync_module
    monkeypatch.setattr(
        sync_module, "_http",
        lambda url, *, token, post=None: peer_app.get("/api/node").text,
    )

    web = TestClient(create_app(home=tmp_path / "local"))
    web.post("/api/peers", json={"url": "http://peer:8000"})
    listed = web.get("/api/peers").json()["peers"]
    assert listed[0]["name"] == "the-peer"
