"""Fleet admin identity (v1.6 Phase 1): Ed25519 grants + signed requests.

The trust model under test:
- a node accepts signed operations ONLY from public keys its local operator
  granted (never adopted from sync — the D1–D4 boundary);
- signatures bind method+path+query+body+timestamp+nonce (no tampering, no
  replay, no cross-route reuse);
- capabilities split management from content: 'manage' can operate the node,
  only 'read-private' can read memory content;
- revocation is immediate; every accepted mutation/content-read is audited.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import crypto, tokens
from agent_memory_os.client import MemoryClient
from agent_memory_os.web_app import FLEET_ROUTE_CAPABILITIES, create_app


@pytest.fixture()
def node(tmp_path):
    """A token-protected node with one manage-only fleet admin granted."""
    home = tmp_path / "node"
    home.mkdir()
    tokens.create_token(home)  # bearer auth engaged -> fleet path exercised
    seed = MemoryClient(home=home)
    private = seed.add("private note", owner="alice", visibility=[])
    archived = seed.add(
        "archived private note", owner="alice", visibility=[],
        expires_at="2000-01-01T00:00:00+00:00",
    )
    seed.run_retention()
    orphan = seed.add("orphan content snippet", owner="external", visibility=["team:missing"])
    keypair = crypto.generate_fleet_keypair()
    seed.store.grant_fleet_admin(keypair["public_key"], ["manage"])
    seed.close()
    app = create_app(home=home)
    with TestClient(app) as http:
        yield {
            "home": home, "http": http, "keypair": keypair,
            "private_id": private.id, "archived_id": archived.id,
            "orphan_id": orphan.id,
        }


def _signed(http, keypair, method, target, body=b""):
    headers = crypto.fleet_sign_headers(keypair, method, target, body)
    if body:
        headers["content-type"] = "application/json"
    return http.request(method, target, headers=headers, content=body or None)


def _grant_caps(node, caps):
    client = MemoryClient(home=node["home"])
    client.store.grant_fleet_admin(node["keypair"]["public_key"], caps)
    client.close()


# --------------------------------------------------------------------------- #
# Key + grant lifecycle
# --------------------------------------------------------------------------- #

def test_keypair_roundtrip(tmp_path):
    keypair = crypto.generate_fleet_keypair()
    crypto.save_fleet_key(tmp_path, keypair)
    loaded = crypto.load_fleet_key(tmp_path)
    assert loaded == keypair
    message = crypto.fleet_canonical_message("GET", "/api/stats", b"", "1", "n")
    assert crypto.fleet_verify(
        keypair["public_key"], message, crypto.fleet_sign(keypair["private_key"], message))


def test_grant_validates_caps(tmp_path):
    client = MemoryClient(home=tmp_path)
    keypair = crypto.generate_fleet_keypair()
    with pytest.raises(ValueError, match="unknown capabilities"):
        client.store.grant_fleet_admin(keypair["public_key"], ["god"])
    with pytest.raises(ValueError, match="capability"):
        client.store.grant_fleet_admin(keypair["public_key"], [])
    client.close()


def test_revoke_and_regrant(tmp_path):
    client = MemoryClient(home=tmp_path)
    keypair = crypto.generate_fleet_keypair()
    grant = client.store.grant_fleet_admin(keypair["public_key"], ["manage"])
    assert client.store.revoke_fleet_admin(grant["key_id"]) is True
    assert client.store.get_fleet_admin(grant["key_id"]) is None
    # re-grant reactivates with new caps
    client.store.grant_fleet_admin(keypair["public_key"], ["manage", "read-private"])
    assert client.store.get_fleet_admin(grant["key_id"])["caps"] == [
        "manage", "read-private"]
    client.close()


# --------------------------------------------------------------------------- #
# Signed requests against the live app
# --------------------------------------------------------------------------- #

def test_signed_get_accepted_with_manage(node):
    response = _signed(node["http"], node["keypair"], "GET", "/api/stats")
    assert response.status_code == 200
    assert "total" in response.json()


def test_unsigned_request_still_401(node):
    assert node["http"].get("/api/stats").status_code == 401


def test_wrong_key_rejected(node):
    stranger = crypto.generate_fleet_keypair()  # never granted
    response = _signed(node["http"], stranger, "GET", "/api/stats")
    assert response.status_code == 403
    assert "unknown or revoked" in response.json()["detail"]


def test_tampered_signature_rejected(node):
    headers = crypto.fleet_sign_headers(node["keypair"], "GET", "/api/stats")
    headers["x-amos-fleet-signature"] = headers["x-amos-fleet-signature"][:-4] + "AAAA"
    response = node["http"].get("/api/stats", headers=headers)
    assert response.status_code == 403
    assert "invalid signature" in response.json()["detail"]


def test_signature_bound_to_route_and_query(node):
    # A signature minted for one target must not authorize another.
    headers = crypto.fleet_sign_headers(node["keypair"], "GET", "/api/stats")
    response = node["http"].get("/api/owners", headers=headers)
    assert response.status_code == 403
    # Query string is covered too.
    headers2 = crypto.fleet_sign_headers(node["keypair"], "GET", "/api/owners?x=1")
    response2 = node["http"].get("/api/owners?x=2", headers=headers2)
    assert response2.status_code == 403


def test_replayed_nonce_rejected(node):
    headers = crypto.fleet_sign_headers(node["keypair"], "GET", "/api/stats")
    assert node["http"].get("/api/stats", headers=headers).status_code == 200
    replay = node["http"].get("/api/stats", headers=headers)
    assert replay.status_code == 403
    assert "replayed nonce" in replay.json()["detail"]


def test_expired_timestamp_rejected(node):
    headers = crypto.fleet_sign_headers(node["keypair"], "GET", "/api/stats")
    stale = str(int(headers["x-amos-fleet-timestamp"]) - 3600)
    message = crypto.fleet_canonical_message(
        "GET", "/api/stats", b"", stale, headers["x-amos-fleet-nonce"])
    headers["x-amos-fleet-timestamp"] = stale
    headers["x-amos-fleet-signature"] = crypto.fleet_sign(
        node["keypair"]["private_key"], message)
    response = node["http"].get("/api/stats", headers=headers)
    assert response.status_code == 403
    assert "expired" in response.json()["detail"]


def test_manage_cannot_read_content_routes(node):
    # /api/memories exposes memory content -> needs read-private.
    response = _signed(node["http"], node["keypair"], "GET", "/api/memories")
    assert response.status_code == 403
    assert "read-private" in response.json()["detail"]


def test_read_private_cap_unlocks_content_and_audits(node):
    _grant_caps(node, ["manage", "read-private"])
    response = _signed(node["http"], node["keypair"], "GET", "/api/memories")
    assert response.status_code == 200
    # The content read is on the node's audit trail, attributed to the key.
    audit = MemoryClient(home=node["home"])
    entries = audit.store.org_audit_log(limit=10)
    audit.close()
    key_id = node["keypair"]["key_id"]
    assert any(e["action"] == "fleet_op" and e["actor"] == f"fleet:{key_id}"
               for e in entries)


def test_signed_mutation_accepted_and_audited(node):
    body = b'{"old_owner": "alice", "new_owner": "bob"}'
    response = _signed(node["http"], node["keypair"], "POST",
                       "/api/owners/reassign", body)
    assert response.status_code == 200
    audit = MemoryClient(home=node["home"])
    entries = audit.store.org_audit_log(limit=10)
    audit.close()
    assert any("POST /api/owners/reassign" in e["detail"] for e in entries)


def test_read_private_alone_cannot_mutate_content_routes(node):
    _grant_caps(node, ["read-private"])
    memory_id = node["private_id"]
    requests = [
        ("POST", "/api/memories", b'{"content":"blocked create","owner":"alice"}'),
        ("PATCH", f"/api/memories/{memory_id}", b'{"content":"blocked patch"}'),
        ("DELETE", f"/api/memories/{memory_id}", b""),
        ("POST", f"/api/memories/{memory_id}/share",
         b'{"actor":"alice","to_agent":"bob"}'),
        ("POST", f"/api/memories/{memory_id}/revoke",
         b'{"actor":"alice","to_agent":"bob"}'),
        ("POST", "/api/recall", b'{"memory_ids":[],"helpful":true}'),
    ]

    for method, target, body in requests:
        response = _signed(node["http"], node["keypair"], method, target, body)
        assert response.status_code == 403, (method, target, response.text)
        assert "manage" in response.json()["detail"]


def test_record_returning_mutations_require_both_caps(node):
    patch_target = f"/api/memories/{node['private_id']}"
    restore_target = f"/api/archive/{node['archived_id']}/restore"

    manage_patch = _signed(
        node["http"], node["keypair"], "PATCH", patch_target,
        b'{"content":"updated private note"}',
    )
    manage_restore = _signed(node["http"], node["keypair"], "POST", restore_target)
    assert manage_patch.status_code == 403
    assert manage_restore.status_code == 403
    assert "read-private" in manage_patch.json()["detail"]
    assert "read-private" in manage_restore.json()["detail"]

    _grant_caps(node, ["manage", "read-private"])
    combined_patch = _signed(
        node["http"], node["keypair"], "PATCH", patch_target,
        b'{"content":"updated private note"}',
    )
    combined_restore = _signed(node["http"], node["keypair"], "POST", restore_target)
    assert combined_patch.status_code == 200
    assert combined_patch.json()["content"] == "updated private note"
    assert combined_restore.status_code == 200
    assert combined_restore.json()["content"] == "archived private note"


def test_orphan_snippets_require_manage_and_read_private(node):
    manage_only = _signed(
        node["http"], node["keypair"], "GET", "/api/maintenance/orphans",
    )
    assert manage_only.status_code == 403
    assert "read-private" in manage_only.json()["detail"]

    _grant_caps(node, ["manage", "read-private"])
    combined = _signed(
        node["http"], node["keypair"], "GET", "/api/maintenance/orphans",
    )
    assert combined.status_code == 200
    orphan = next(item for item in combined.json()["orphans"]
                  if item["id"] == node["orphan_id"])
    assert orphan["content"] == "orphan content snippet"


def test_orphan_deletion_requires_manage_only(node):
    response = _signed(
        node["http"], node["keypair"], "POST",
        "/api/maintenance/orphans/delete?confirm=orphans",
    )
    assert response.status_code == 200
    assert response.json()["orphans_deleted"] == 1


def test_every_api_operation_has_explicit_fleet_classification(tmp_path):
    app = create_app(home=tmp_path)
    registered = {
        (method, route.path)
        for route in app.routes
        if str(getattr(route, "path", "")).startswith("/api/")
        for method in (getattr(route, "methods", None) or set())
    }
    assert registered == set(FLEET_ROUTE_CAPABILITIES)


def test_unclassified_api_route_is_denied_to_fleet_signature(tmp_path):
    home = tmp_path / "node"
    home.mkdir()
    tokens.create_token(home)
    keypair = crypto.generate_fleet_keypair()
    client = MemoryClient(home=home)
    client.store.grant_fleet_admin(keypair["public_key"], ["manage", "read-private"])
    client.close()
    app = create_app(home=home)

    @app.get("/api/new-unclassified-route")
    def unclassified():
        return {"should_not": "run"}

    with TestClient(app) as http:
        response = _signed(http, keypair, "GET", "/api/new-unclassified-route")
    assert response.status_code == 403
    assert "not authorized for fleet access" in response.json()["detail"]


def test_console_does_not_amplify_manage_into_private_read(tmp_path, monkeypatch):
    from agent_memory_os import fleet as fleet_mod

    home = tmp_path / "console"
    home.mkdir()
    tokens.create_token(home)
    downstream_key = crypto.generate_fleet_keypair()
    crypto.save_fleet_key(home, downstream_key)
    caller_key = crypto.generate_fleet_keypair()
    client = MemoryClient(home=home)
    client.store.add_peer("http://node-a:8000", policy="shared")
    client.store.grant_fleet_admin(caller_key["public_key"], ["manage"])
    client.close()

    calls = []

    def private_response(keypair, url, method, target, payload=None):
        calls.append((keypair["key_id"], url, method, target, payload))
        return 200, {"memories": [{"content": "downstream private"}]}

    monkeypatch.setattr(fleet_mod, "signed_call", private_response)
    browse = "/api/fleet/browse?url=http%3A%2F%2Fnode-a%3A8000"
    proxy = (
        "/api/fleet/proxy?url=http%3A%2F%2Fnode-a%3A8000"
        "&path=%2Fapi%2Fmemories"
    )
    with TestClient(create_app(home=home)) as http:
        denied_browse = _signed(http, caller_key, "GET", browse)
        denied_proxy = _signed(http, caller_key, "GET", proxy)
        assert denied_browse.status_code == 403
        assert denied_proxy.status_code == 403
        assert "read-private" in denied_browse.json()["detail"]
        assert "read-private" in denied_proxy.json()["detail"]
        assert calls == []

        grantor = MemoryClient(home=home)
        grantor.store.grant_fleet_admin(
            caller_key["public_key"], ["manage", "read-private"]
        )
        grantor.close()
        allowed_browse = _signed(http, caller_key, "GET", browse)
        allowed_proxy = _signed(http, caller_key, "GET", proxy)

    assert allowed_browse.status_code == 200
    assert allowed_proxy.status_code == 200
    assert allowed_browse.json()["memories"][0]["content"] == "downstream private"
    assert allowed_proxy.json()["memories"][0]["content"] == "downstream private"
    assert len(calls) == 2


def test_revocation_is_immediate(node):
    client = MemoryClient(home=node["home"])
    client.store.revoke_fleet_admin(node["keypair"]["key_id"])
    client.close()
    response = _signed(node["http"], node["keypair"], "GET", "/api/stats")
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Trust boundary: grants never arrive over sync
# --------------------------------------------------------------------------- #

def test_sync_bundle_cannot_carry_fleet_grants(tmp_path):
    """A malicious peer must not be able to grant itself fleet admin by
    crafting a bundle: the bundle format has no fleet_admins channel, and
    import must leave the table untouched."""
    from agent_memory_os.sync import export_bundle, import_bundle

    a = MemoryClient(home=tmp_path / "a")
    a.add("seed", owner="x", visibility=["global"])
    bundle_path = tmp_path / "bundle.jsonl"
    export_bundle(a.store, bundle_path)
    # Append hostile lines resembling every plausible smuggling shape.
    hostile = bundle_path.read_text(encoding="utf-8") + (
        '\n{"kind": "fleet_admin", "key_id": "evil", "public_key": "AAAA", "caps": "[\\"manage\\"]"}'
        '\n{"fleet_admins": [{"key_id": "evil2", "public_key": "BBBB"}]}\n'
    )
    hostile_path = tmp_path / "hostile.jsonl"
    hostile_path.write_text(hostile, encoding="utf-8")
    b = MemoryClient(home=tmp_path / "b")
    try:
        import_bundle(b.store, hostile_path)
    except Exception:  # noqa: BLE001 - rejecting outright is also acceptable
        pass
    assert b.store.list_fleet_admins() == []
    a.close()
    b.close()


# --------------------------------------------------------------------------- #
# Phase 2: console fan-out + aggregation
# --------------------------------------------------------------------------- #

def _bridge_fleet_http(clients_by_url):
    """Route fleet._http_request through TestClients keyed by base url."""
    def _request(url, method, target, body, headers, *, timeout=10):
        base = url.rstrip("/")
        http = clients_by_url.get(base)
        if http is None:
            return 0, "connection refused"
        response = http.request(method, target, headers=headers,
                                content=body or None)
        return response.status_code, response.text
    return _request


@pytest.fixture()
def small_fleet(tmp_path, monkeypatch):
    """Console + node-a (granted) + node-b (up, NOT granted) + node-x (down)."""
    from agent_memory_os import fleet as fleet_mod

    keypair = crypto.generate_fleet_keypair()

    def make_node(name, grant):
        home = tmp_path / name
        home.mkdir()
        tokens.create_token(home)
        seed = MemoryClient(home=home)
        seed.add(f"note on {name}", owner=name, visibility=[])
        if grant:
            seed.store.grant_fleet_admin(keypair["public_key"], ["manage"])
        seed.close()
        return TestClient(create_app(home=home))

    with make_node("node-a", grant=True) as a, make_node("node-b", grant=False) as b:
        console_home = tmp_path / "console"
        console_home.mkdir()
        crypto.save_fleet_key(console_home, keypair)
        console = MemoryClient(home=console_home)
        console.store.add_peer("http://node-a:8000", policy="shared", name="alpha")
        console.store.add_peer("http://node-b:8000", policy="shared", name="beta")
        console.store.add_peer("http://node-x:8000", policy="shared", name="ghost")
        monkeypatch.setattr(fleet_mod, "_http_request", _bridge_fleet_http({
            "http://node-a:8000": a, "http://node-b:8000": b,
        }))
        yield {"console": console, "home": console_home, "keypair": keypair}
        console.close()


def test_fleet_status_aggregates_and_degrades(small_fleet):
    from agent_memory_os.fleet import fleet_status

    report = fleet_status(small_fleet["console"], small_fleet["home"])
    assert report["console"]["key_id"] == small_fleet["keypair"]["key_id"]
    by_name = {n["name"]: n for n in report["nodes"]}
    # granted node: fully aggregated
    alpha = by_name["alpha"]
    assert alpha["reachable"] and alpha["authorized"]
    assert alpha["memories"] == 1 and alpha["version"]
    assert [o["owner"] for o in alpha["owners"]] == ["node-a"]
    # up-but-not-granted node: visible, marked unauthorized, reason surfaced
    beta = by_name["beta"]
    assert beta["reachable"] and not beta["authorized"]
    assert "fleet" in beta["detail"] or "HTTP" in beta["detail"]
    # down node: reachable=False, nothing else claimed
    ghost = by_name["ghost"]
    assert not ghost["reachable"] and ghost["memories"] is None


def test_fleet_trigger_sync_runs_on_granted_nodes(small_fleet):
    from agent_memory_os.fleet import fleet_trigger

    results = {r["name"]: r for r in
               fleet_trigger(small_fleet["console"], small_fleet["home"], "sync")}
    assert results["alpha"]["ok"] is True
    assert results["beta"]["ok"] is False      # no grant -> 403
    assert results["ghost"]["ok"] is False     # down -> status 0


def test_fleet_trigger_single_node_and_unknown(small_fleet):
    from agent_memory_os.fleet import fleet_trigger

    results = fleet_trigger(small_fleet["console"], small_fleet["home"], "sync",
                            only_url="http://node-a:8000")
    assert len(results) == 1 and results[0]["ok"]
    with pytest.raises(ValueError, match="no registered peer"):
        fleet_trigger(small_fleet["console"], small_fleet["home"], "sync",
                      only_url="http://nowhere:1")


def test_fleet_status_requires_console_key(tmp_path):
    from agent_memory_os.fleet import FleetKeyMissing, fleet_status

    client = MemoryClient(home=tmp_path)
    with pytest.raises(FleetKeyMissing):
        fleet_status(client, tmp_path)
    client.close()


# --------------------------------------------------------------------------- #
# Phase 4: the console's own web endpoints
# --------------------------------------------------------------------------- #

def test_web_fleet_status_unconfigured(tmp_path):
    app = create_app(home=tmp_path)
    http = TestClient(app)
    data = http.get("/api/fleet/status").json()
    assert data["configured"] is False
    assert "fleet keygen" in data["hint"]


def test_web_fleet_status_configured(small_fleet):
    # Serve a console app over the SAME home that holds the fleet key + peers.
    app = create_app(home=small_fleet["home"])
    http = TestClient(app)
    data = http.get("/api/fleet/status").json()
    assert data["configured"] is True
    assert data["console"]["key_id"] == small_fleet["keypair"]["key_id"]
    by_name = {n["name"]: n for n in data["nodes"]}
    assert by_name["alpha"]["authorized"] is True
    assert by_name["ghost"]["reachable"] is False


def test_web_fleet_trigger_sync(small_fleet):
    app = create_app(home=small_fleet["home"])
    http = TestClient(app)
    r = http.post("/api/fleet/trigger",
                  json={"action": "sync", "url": "http://node-a:8000"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1 and results[0]["ok"] is True
    # unknown action rejected at the model layer
    assert http.post("/api/fleet/trigger", json={"action": "explode"}).status_code == 422


def test_web_fleet_browse_requires_read_private_then_works(small_fleet):
    app = create_app(home=small_fleet["home"])
    http = TestClient(app)
    # node-a granted manage only -> the target node refuses the content read
    # and the console surfaces that refusal (not a silent empty list).
    r = http.get("/api/fleet/browse", params={"url": "http://node-a:8000"})
    assert r.status_code == 403
    assert "read-private" in r.json()["detail"]
    # grant read-private on node-a -> live remote read works
    grantor = MemoryClient(home=small_fleet["home"].parent / "node-a")
    grantor.store.grant_fleet_admin(small_fleet["keypair"]["public_key"],
                                    ["manage", "read-private"])
    grantor.close()
    r2 = http.get("/api/fleet/browse", params={"url": "http://node-a:8000"})
    assert r2.status_code == 200
    memories = r2.json()["memories"]
    assert [m["owner"] for m in memories] == ["node-a"]
    assert "note on node-a" in memories[0]["content"]
    # owner filter passes through
    r3 = http.get("/api/fleet/browse",
                  params={"url": "http://node-a:8000", "owner": "nobody"})
    assert r3.status_code == 200 and r3.json()["memories"] == []
    # unreachable node -> 502, not a hang or crash
    r4 = http.get("/api/fleet/browse", params={"url": "http://node-x:8000"})
    assert r4.status_code == 502


def test_update_trigger_carries_confirm_echo():
    """update-run refuses without ?confirm=update; the console must supply it
    (found live: fleet update failed fleet-wide with HTTP 400 without this)."""
    from agent_memory_os.fleet import TRIGGER_TARGETS

    method, path = TRIGGER_TARGETS["update"]
    assert method == "POST" and "confirm=update" in path


# --------------------------------------------------------------------------- #
# Remote management mode: the console-side signed proxy
# --------------------------------------------------------------------------- #

def _console_http(small_fleet):
    return TestClient(create_app(home=small_fleet["home"]))


def test_fleet_proxy_forwards_get_and_post(small_fleet):
    # read-private needed for the remote memories read
    grantor = MemoryClient(home=small_fleet["home"].parent / "node-a")
    grantor.store.grant_fleet_admin(small_fleet["keypair"]["public_key"],
                                    ["manage", "read-private"])
    grantor.close()
    http = _console_http(small_fleet)
    r = http.get("/api/fleet/proxy",
                 params={"url": "http://node-a:8000", "path": "/api/memories?limit=5"})
    assert r.status_code == 200
    assert [m["owner"] for m in r.json()["memories"]] == ["node-a"]
    # mutation forwards too (owner reassign on the REMOTE node)
    r2 = http.post(
        "/api/fleet/proxy",
        params={"url": "http://node-a:8000", "path": "/api/owners/reassign"},
        json={"old_owner": "node-a", "new_owner": "renamed"},
    )
    assert r2.status_code == 200
    assert r2.json()["changed"]["memories_owner"] == 1
    # and the remote node audited the fleet operation, attributed to the key
    remote = MemoryClient(home=small_fleet["home"].parent / "node-a")
    entries = remote.store.org_audit_log(limit=10)
    remote.close()
    key_id = small_fleet["keypair"]["key_id"]
    assert any(e["actor"] == f"fleet:{key_id}" and "owners/reassign" in e["detail"]
               for e in entries)


def test_fleet_proxy_guard_rails(small_fleet):
    http = _console_http(small_fleet)
    # unregistered target refused (no open forwarder)
    r = http.get("/api/fleet/proxy",
                 params={"url": "http://evil:9999", "path": "/api/stats"})
    assert r.status_code == 400 and "registered peer" in r.json()["detail"]
    # non-/api/ path refused
    r2 = http.get("/api/fleet/proxy",
                  params={"url": "http://node-a:8000", "path": "/healthz"})
    assert r2.status_code == 400
    # no proxy recursion
    r3 = http.get("/api/fleet/proxy",
                  params={"url": "http://node-a:8000",
                          "path": "/api/fleet/status"})
    assert r3.status_code == 400
    # unreachable registered peer -> 502
    r4 = http.get("/api/fleet/proxy",
                  params={"url": "http://node-x:8000", "path": "/api/stats"})
    assert r4.status_code == 502


def test_fleet_proxy_surfaces_remote_capability_denial(small_fleet):
    # node-a granted manage only in the fixture: content read denied REMOTELY,
    # and the console surfaces that status instead of masking it.
    http = _console_http(small_fleet)
    r = http.get("/api/fleet/proxy",
                 params={"url": "http://node-a:8000", "path": "/api/memories"})
    assert r.status_code == 403
    assert "read-private" in str(r.json()["detail"])
