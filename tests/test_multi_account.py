"""Multi-account-on-one-host features: pairing, discovery, status, services.

Covers the v1.3 theme end to end:
- one-time pairing invites (hash-only storage, TTL, atomic single-use)
- the full invite → redeem → join exchange (via the real FastAPI app)
- same-host discovery over /healthz
- per-account Windows task names (launchd/systemd need none — per-user domains)
- `service install` picking + persisting a free port
- `status` / `neighbors` CLI surfaces
"""

from __future__ import annotations

import json
import re
import socket
import threading
from datetime import UTC, datetime

import pytest

import agent_memory_os.db as db_module
from agent_memory_os import pairing
from agent_memory_os import service as svc
from agent_memory_os.client import MemoryClient
from agent_memory_os.discovery import probe_node, scan_local_nodes
from agent_memory_os.timestamp_converters import dt_to_stamp

_CANONICAL_UTC_RE = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}Z"
)


# --------------------------------------------------------------------------- #
# Invite store semantics
# --------------------------------------------------------------------------- #

def test_invite_issue_and_consume(tmp_path):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    time-helper: changed c8353b42@db-schema-v21.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    invite = pairing.issue_invite(client, "apollo", ttl_seconds=60)
    assert invite["code"].startswith(pairing.CODE_PREFIX)
    assert re.fullmatch(_CANONICAL_UTC_RE, invite["expires_at"])

    code_hash = pairing._hash_code(invite["code"])
    got = client.store.consume_pairing_invite(code_hash, redeemed_by="node-b")
    assert got and got["team_id"] == "apollo"
    row = client.store.conn.execute(
        "SELECT created_at, expires_at, used_at FROM pairing_invites WHERE code_hash = ?",
        (code_hash,),
    ).fetchone()
    assert re.fullmatch(_CANONICAL_UTC_RE, row["created_at"])
    assert re.fullmatch(_CANONICAL_UTC_RE, row["expires_at"])
    assert re.fullmatch(_CANONICAL_UTC_RE, row["used_at"])
    # single-use: a second redemption of the same code must fail
    assert client.store.consume_pairing_invite(code_hash, redeemed_by="node-c") is None
    client.close()


def test_invite_expiry_and_unknown_team(tmp_path):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    with pytest.raises(ValueError, match="unknown team"):
        pairing.issue_invite(client, "no-such-team")
    with pytest.raises(ValueError, match="positive"):
        client.store.create_pairing_invite("apollo", "h", ttl_seconds=0)

    # Expired invites are unredeemable: backdate expires_at directly.
    invite = pairing.issue_invite(client, "apollo", ttl_seconds=60)
    client.store.conn.execute(
        "UPDATE pairing_invites SET expires_at = '2000-01-01T00:00:00+00:00'")
    client.store.conn.commit()
    assert client.store.consume_pairing_invite(
        pairing._hash_code(invite["code"]), redeemed_by="x") is None
    client.close()


def test_pairing_invite_ttl_computes_exact_expiry(tmp_path, monkeypatch):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 4279c380@db-schema-v21.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    fixed_now = datetime(2026, 8, 11, 12, 0, 0, 500000, tzinfo=UTC)
    fixed_stamp = dt_to_stamp(fixed_now)
    monkeypatch.setattr(db_module, "utc_now_dt", lambda: fixed_now)

    explicit = client.store.create_pairing_invite(
        "apollo",
        "explicit-ttl",
        ttl_seconds=60,
    )
    default = client.store.create_pairing_invite("apollo", "default-ttl")

    assert explicit["expires_at"] == "2026-08-11T12:01:00.500000Z"
    assert default["expires_at"] == "2026-08-11T12:10:00.500000Z"
    rows = client.store.conn.execute(
        "SELECT code_hash, created_at, expires_at FROM pairing_invites "
        "ORDER BY code_hash"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        (
            "default-ttl",
            fixed_stamp,
            "2026-08-11T12:10:00.500000Z",
        ),
        (
            "explicit-ttl",
            fixed_stamp,
            "2026-08-11T12:01:00.500000Z",
        ),
    ]
    client.close()


def test_pairing_invite_redemption_uses_strict_expiry_boundary(
    tmp_path,
    monkeypatch,
):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 4279c380@db-schema-v21.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    clock = {"now": datetime(2026, 8, 11, 12, 0, 0, 500000, tzinfo=UTC)}
    monkeypatch.setattr(db_module, "utc_now_dt", lambda: clock["now"])
    monkeypatch.setattr(db_module, "utc_now_stamp", lambda: dt_to_stamp(clock["now"]))
    for code_hash in ("before-expiry", "at-expiry", "after-expiry"):
        client.store.create_pairing_invite(
            "apollo",
            code_hash,
            ttl_seconds=60,
        )

    clock["now"] = datetime(2026, 8, 11, 12, 1, 0, 499999, tzinfo=UTC)
    redeemed = client.store.consume_pairing_invite(
        "before-expiry",
        redeemed_by="before-node",
    )
    assert redeemed is not None
    assert redeemed["team_id"] == "apollo"

    clock["now"] = datetime(2026, 8, 11, 12, 1, 0, 500000, tzinfo=UTC)
    assert client.store.consume_pairing_invite(
        "at-expiry",
        redeemed_by="at-node",
    ) is None

    clock["now"] = datetime(2026, 8, 11, 12, 1, 0, 500001, tzinfo=UTC)
    assert client.store.consume_pairing_invite(
        "after-expiry",
        redeemed_by="after-node",
    ) is None
    rows = client.store.conn.execute(
        "SELECT code_hash, used_at FROM pairing_invites ORDER BY code_hash"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("after-expiry", None),
        ("at-expiry", None),
        ("before-expiry", "2026-08-11T12:01:00.499999Z"),
    ]
    client.close()


def test_wrong_code_is_rejected(tmp_path):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    pairing.issue_invite(client, "apollo")
    assert client.store.consume_pairing_invite(
        pairing._hash_code("amos_join_forged"), redeemed_by="x") is None
    client.close()


# --------------------------------------------------------------------------- #
# Full pairing exchange through the real web app
# --------------------------------------------------------------------------- #

@pytest.fixture()
def inviter(tmp_path):
    """A real inviter app (with admin token set, proving the exemption works)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient as HttpClient

    from agent_memory_os import tokens
    from agent_memory_os.web_app import create_app

    home = tmp_path / "inviter"
    tokens.create_token(home)  # console is token-protected
    app = create_app(home)
    with HttpClient(app) as http:
        client = MemoryClient(home=home)
        client.store.create_team("apollo")
        yield {"home": home, "http": http, "client": client}
        client.close()


def _bridge_post(http):
    """Route pairing's urllib POST through the TestClient."""
    def _post(url, body, *, timeout=15):
        response = http.post(pairing.REDEEM_PATH, json=body)
        if response.status_code != 200:
            import urllib.error

            raise urllib.error.HTTPError(url, response.status_code,
                                         response.text, hdrs=None, fp=None)
        return response.json()
    return _post


def test_join_full_exchange(inviter, tmp_path, monkeypatch):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16; 013a45cb@db-schema-v16.
    """
    from agent_memory_os import crypto, tokens

    # The inviter uses an encrypted mesh.
    crypto.save_sync_secret(inviter["home"], "amos_sk_mesh-secret")
    invite = pairing.issue_invite(inviter["client"], "apollo")
    monkeypatch.setattr(pairing, "_post_redeem", _bridge_post(inviter["http"]))

    joiner_home = tmp_path / "joiner"
    joiner = MemoryClient(home=joiner_home)
    report = pairing.join_with_code(
        joiner, invite["code"], "http://127.0.0.1:9999",
        agent_id="account-b", my_url="http://127.0.0.1:8010",
        node_name="node-b", home=joiner_home,
    )

    # Joiner side: team-scoped peer + inviter's sync token + mesh key.
    assert report["team_id"] == "apollo"
    peers = joiner.store.list_peers()
    assert peers and peers[0]["policy"] == "team:apollo"
    assert peers[0]["has_token"] is True
    their_token = joiner.store.peer_token("http://127.0.0.1:9999")
    assert their_token and their_token.startswith("amos_sync_")
    assert report["sync_key_installed"] is True
    assert crypto.load_sync_secret(joiner_home) == "amos_sk_mesh-secret"

    # Inviter side: agent-b joined the team, joiner registered as a peer
    # under the SAME team policy, holding the joiner's sync token.
    team = inviter["client"].store.get_team("apollo")
    assert "account-b" in (team.get("members") or [])
    inviter_peers = inviter["client"].store.list_peers()
    assert inviter_peers and inviter_peers[0]["url"] == "http://127.0.0.1:8010"
    assert inviter_peers[0]["policy"] == "team:apollo"
    got_joiner_token = inviter["client"].store.peer_token("http://127.0.0.1:8010")
    assert got_joiner_token == tokens.load_token(joiner_home, tier="sync")

    # Inviter registers the joiner as an AGENT (not just a team member), so it
    # shows in the Agents tab instead of being an invisible member id.
    inviter_agents = {a["id"] for a in inviter["client"].store.list_agents()}
    assert "account-b" in inviter_agents

    # Joiner records the team + its OWN membership locally (immediately visible
    # in the Teams tab, not only after sync converges).
    joined_team = joiner.store.get_team("apollo")
    assert joined_team is not None
    assert "account-b" in (joined_team.get("members") or [])
    # ...and registers the inviter as a team member/agent from the response id.
    joiner_agents = {a["id"] for a in joiner.store.list_agents()}
    inviter_self = inviter["client"].node_name
    assert inviter_self in joiner_agents
    assert inviter_self in (joined_team.get("members") or [])

    # The code died with the exchange.
    with pytest.raises(ValueError, match="refused"):
        pairing.join_with_code(
            joiner, invite["code"], "http://127.0.0.1:9999",
            agent_id="account-c", home=joiner_home,
        )
    joiner.close()


def test_join_rejects_mismatched_sync_key(inviter, tmp_path, monkeypatch):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    from agent_memory_os import crypto

    crypto.save_sync_secret(inviter["home"], "amos_sk_key-A")
    invite = pairing.issue_invite(inviter["client"], "apollo")
    monkeypatch.setattr(pairing, "_post_redeem", _bridge_post(inviter["http"]))

    joiner_home = tmp_path / "joiner2"
    crypto.save_sync_secret(joiner_home, "amos_sk_key-B")  # conflicting mesh
    joiner = MemoryClient(home=joiner_home)
    with pytest.raises(ValueError, match="different sync key"):
        pairing.join_with_code(
            joiner, invite["code"], "http://127.0.0.1:9999",
            agent_id="account-b", home=joiner_home,
        )
    joiner.close()


def test_redeem_endpoint_is_opaque_and_exempt(inviter):
    """No bearer token needed; bad codes get one indistinguishable 403.

    Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    http = inviter["http"]
    body = {"code": "amos_join_wrong-code-entirely",
            "envelope": pairing.encrypt_payload({"agent_id": "x"}, "amos_join_wrong-code-entirely")}
    response = http.post(pairing.REDEEM_PATH, json=body)
    assert response.status_code == 403
    assert response.json()["detail"] == "pairing refused"

    # Other /api routes remain token-gated (the exemption is surgical).
    assert http.get("/api/memories").status_code in (401, 403)


def test_redeem_garbage_envelope(inviter):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    invite = pairing.issue_invite(inviter["client"], "apollo")
    response = inviter["http"].post(
        pairing.REDEEM_PATH, json={"code": invite["code"], "envelope": "AMOSENC1:junk"})
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

@pytest.fixture()
def fake_amos_server():
    """Minimal loopback HTTP server answering /healthz like a real node."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                body = json.dumps({"status": "ok", "node": "other-account",
                                   "integrity": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):  # silence
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


def test_probe_and_scan_find_amos_node(fake_amos_server):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    port = fake_amos_server
    probe = probe_node(f"http://127.0.0.1:{port}")
    assert probe.is_amos and probe.node_name == "other-account"

    nodes = scan_local_nodes(ports=[port])
    assert [n.node_name for n in nodes] == ["other-account"]
    # excluded port (self) is skipped
    assert scan_local_nodes(ports=[port], exclude_ports={port}) == []


def test_scan_ignores_non_amos_listener():
    """A listener that isn't AMOS (no /healthz `node`) is not reported.

    Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>hi</html>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert scan_local_nodes(ports=[server.server_address[1]]) == []
    finally:
        server.shutdown()


# --------------------------------------------------------------------------- #
# Per-account service naming + port persistence
# --------------------------------------------------------------------------- #

def test_windows_task_name_is_per_account(monkeypatch):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    import getpass

    monkeypatch.setattr(getpass, "getuser", lambda: "Alice Wu")
    assert svc.windows_task_name() == "agent-memory-web-Alice-Wu"
    monkeypatch.setattr(getpass, "getuser", lambda: "簡")
    assert svc.windows_task_name() == "agent-memory-web-user"  # non-ascii falls back


def test_schtasks_uses_per_account_name(monkeypatch, tmp_path):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    import getpass

    monkeypatch.setattr(getpass, "getuser", lambda: "bob")
    config = svc.make_config(tmp_path, "127.0.0.1", 8000)
    create = svc.build_schtasks_create(config)
    assert create[create.index("/TN") + 1] == "agent-memory-web-bob"

    # uninstall removes BOTH the per-account and the legacy bare name
    actions = svc.uninstall(platform="win32", dry_run=True)
    joined = "\n".join(actions)
    assert "agent-memory-web-bob" in joined
    assert "/TN agent-memory-web /F" in joined


def test_service_install_persists_free_port(tmp_path, capsys):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    from agent_memory_os.cli import main
    from agent_memory_os.settings import (
        load_instance_settings,
        update_instance_settings,
    )

    # Occupy this home's configured port so install must move on.
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]
    update_instance_settings(tmp_path, port=taken)
    try:
        rc = main(["--home", str(tmp_path), "service", "install", "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert f"port {taken} is taken" in out
        # dry-run must not persist
        assert load_instance_settings(tmp_path).port == taken
    finally:
        blocker.close()


# --------------------------------------------------------------------------- #
# status / neighbors CLI surfaces
# --------------------------------------------------------------------------- #

def test_status_json_reports_service_and_peers(tmp_path, capsys):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    from agent_memory_os.cli import main

    client = MemoryClient(home=tmp_path)
    client.store.add_peer("http://127.0.0.1:59999", policy="shared", name="ghost")
    client.close()

    rc = main(["--home", str(tmp_path), "status", "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["local"]["version"]
    assert report["local"]["service"]["platform"]
    assert report["peers"][0]["name"] == "ghost"
    assert report["peers"][0]["online"] is False  # nothing listens there


def test_neighbors_cli_lists_fake_node(tmp_path, capsys, fake_amos_server):
    """Lineage:
    main: introduced 68e82ed2@db-schema-v16.
    """
    from agent_memory_os.cli import main

    port = fake_amos_server
    rc = main(["--home", str(tmp_path), "neighbors", "--json",
               "--ports", f"{port}-{port}"])
    assert rc == 0
    nodes = json.loads(capsys.readouterr().out)
    assert nodes and nodes[0]["node_name"] == "other-account"


def test_redeem_rejects_plaintext_envelope(inviter):
    """Envelope must be a real AMOSENC1 blob; plaintext JSON is refused.

    Lineage:
    main: introduced 7a5acb4d@db-schema-v16.
    """
    invite = pairing.issue_invite(inviter["client"], "apollo")
    r = inviter["http"].post(
        pairing.REDEEM_PATH,
        json={"code": invite["code"],
              "envelope": json.dumps({"agent_id": "x"})})  # not encrypted
    assert r.status_code == 403
    # the invite was NOT burned by the malformed attempt — a real join still works
    import agent_memory_os.pairing as hp
    hp._post_redeem = _bridge_post(inviter["http"])
    b = MemoryClient(home=inviter["home"].parent / "joiner-after-reject")
    rep = pairing.join_with_code(b, invite["code"], "http://127.0.0.1:9",
                                 agent_id="acct-late", home=str(b.store.path.parent))
    assert rep["team_id"] == "apollo"
    b.close()


def test_bad_code_does_not_burn_a_valid_invite(inviter, monkeypatch):
    """A wrong code must not consume anyone else's invite (decrypt/validate
    happens before consume, and consume is keyed on the code's own hash).

    Lineage:
    main: introduced 7a5acb4d@db-schema-v16.
    """
    invite = pairing.issue_invite(inviter["client"], "apollo")
    r = inviter["http"].post(
        pairing.REDEEM_PATH,
        json={"code": "amos_join_wrong",
              "envelope": pairing.encrypt_payload({"agent_id": "x"}, "amos_join_wrong")})
    assert r.status_code == 403
    # original invite still redeemable
    monkeypatch.setattr(pairing, "_post_redeem", _bridge_post(inviter["http"]))
    b = MemoryClient(home=inviter["home"].parent / "joiner-valid")
    rep = pairing.join_with_code(b, invite["code"], "http://127.0.0.1:9",
                                 agent_id="acct-ok", home=str(b.store.path.parent))
    assert rep["team_id"] == "apollo"
    b.close()


def test_join_refuses_plain_http_to_remote_host(tmp_path):
    """Non-loopback http:// is refused unless allow_insecure.

    Lineage:
    main: introduced 7a5acb4d@db-schema-v16; 2cf92e51@db-schema-v17.
    """
    from agent_memory_os import pairing as p
    home = tmp_path / "amos-join-guard"
    client = MemoryClient(home=home)
    with pytest.raises(ValueError, match="plain HTTP"):
        p.join_with_code(client, "amos_join_x", "http://10.0.0.5:8000",
                         agent_id="a", home=str(home))
    client.close()


def test_join_and_register_peer_is_atomic(tmp_path):
    """A bad peer URL rolls back the whole join (no ghost team member).

    Lineage:
    main: introduced 7a5acb4d@db-schema-v16.
    """
    client = MemoryClient(home=tmp_path)
    client.store.create_team("apollo")
    with pytest.raises(ValueError, match="peer URL"):
        client.store.join_team_and_register_peer(
            "apollo", "ghost", peer_url="not-a-url")
    assert "ghost" not in (client.store.get_team("apollo").get("members") or [])
    client.close()
