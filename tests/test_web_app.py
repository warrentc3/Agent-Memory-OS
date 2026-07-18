from fastapi.testclient import TestClient

from agent_memory_os.web_app import create_app


def test_web_ui_root_is_openable_and_shows_stats(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AgentMemoryOS Web UI" in response.text
    assert "Total memories" in response.text


def test_web_api_can_add_and_search_memory(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)

    add_response = client.post(
        "/api/memories",
        json={
            "content": "Web UI smoke test memory for Traditional Chinese output.",
            "owner": "mizuki",
            "scope": "user",
            "type": "preference",
            "tags": ["ui", "smoke"],
            "importance": 0.9,
        },
    )
    assert add_response.status_code == 200
    assert add_response.json()["id"].startswith("mem_")

    search_response = client.get("/api/search", params={"q": "Traditional Chinese", "owner": "mizuki"})

    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["query"] == "Traditional Chinese"
    assert payload["results"][0]["content"] == "Web UI smoke test memory for Traditional Chinese output."
    assert payload["results"][0]["owner"] == "mizuki"


def test_web_api_search_enforces_requester_acl(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    secret = "Private emotional preference only for the owner."
    client.post(
        "/api/memories",
        json={"content": secret, "owner": "mizuki", "visibility": []},
    )
    client.post(
        "/api/memories",
        json={"content": "Public preference note.", "owner": "mizuki", "visibility": ["global"]},
    )

    neo_view = client.get(
        "/api/search", params={"q": "preference", "requester_agent_id": "neo"}
    ).json()
    mizuki_view = client.get(
        "/api/search", params={"q": "preference", "requester_agent_id": "mizuki"}
    ).json()

    neo_contents = [result["content"] for result in neo_view["results"]]
    mizuki_contents = [result["content"] for result in mizuki_view["results"]]
    assert secret not in neo_contents
    assert "Public preference note." in neo_contents
    assert secret in mizuki_contents


def test_web_api_context_pack_enforces_requester_acl(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    secret = "Private ritual reflection kept for the owner."
    client.post("/api/memories", json={"content": secret, "owner": "mizuki", "visibility": []})
    client.post(
        "/api/memories",
        json={"content": "Public ritual checklist.", "owner": "mizuki", "visibility": ["global"]},
    )

    response = client.get(
        "/api/context-pack", params={"q": "ritual", "requester_agent_id": "neo"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert secret not in payload["text"]
    assert "Public ritual checklist." in payload["text"]
    assert all(decision["memory_id"] for decision in payload["decisions"])


def test_web_api_validates_inputs(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)

    bad_scope = client.post("/api/memories", json={"content": "x", "scope": "kingdom"})
    bad_type = client.post("/api/memories", json={"content": "x", "type": "gossip"})
    bad_confidence = client.post("/api/memories", json={"content": "x", "confidence": 5.0})
    bad_decay = client.post("/api/memories", json={"content": "x", "decay_policy": "sideways"})

    assert bad_scope.status_code == 422
    assert bad_type.status_code == 422
    assert bad_confidence.status_code == 422
    assert bad_decay.status_code == 400


def test_web_api_links_and_recall_roundtrip(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    a = client.post(
        "/api/memories",
        json={"content": "Staging deploy failed with database lock.", "visibility": ["global"]},
    ).json()
    b = client.post(
        "/api/memories",
        json={"content": "Snapshot rule before schema changes.", "visibility": ["global"]},
    ).json()

    link_response = client.post(
        "/api/links",
        json={"src_id": a["id"], "dst_id": b["id"], "relation": "caused_by", "weight": 0.8},
    )
    assert link_response.status_code == 200

    links_response = client.get(f"/api/memories/{a['id']}/links")
    assert links_response.status_code == 200
    assert links_response.json()["links"][0]["relation"] == "caused_by"

    recall_response = client.post("/api/recall", json={"memory_ids": [a["id"], b["id"]]})
    assert recall_response.status_code == 200
    assert recall_response.json()["reinforced_links"] == 1

    missing_link = client.post("/api/links", json={"src_id": a["id"], "dst_id": "mem_missing"})
    assert missing_link.status_code == 404
    bad_relation = client.post(
        "/api/links", json={"src_id": a["id"], "dst_id": b["id"], "relation": "friends"}
    )
    assert bad_relation.status_code == 422


def test_web_api_get_memory_and_consolidate(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    created = client.post(
        "/api/memories",
        json={"content": "Docker deploy uses port 8000.", "visibility": ["global"]},
    ).json()
    client.post(
        "/api/memories",
        json={"content": "Docker deploy uses port 8000.", "visibility": ["global"]},
    )

    fetched = client.get(f"/api/memories/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["visibility"] == ["global"]
    assert client.get("/api/memories/mem_missing").status_code == 404

    consolidated = client.post("/api/consolidate")
    assert consolidated.status_code == 200
    assert consolidated.json()["duplicates_merged"] == 1
    assert client.get("/api/stats").json()["total"] == 1


def test_web_api_rejects_non_iso_expires_at(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)

    bad = client.post("/api/memories", json={"content": "x", "expires_at": "12/31/2026"})
    epoch = client.post("/api/memories", json={"content": "x", "expires_at": "1767225600"})
    good = client.post(
        "/api/memories", json={"content": "x", "expires_at": "2030-01-01T00:00:00+00:00"}
    )

    assert bad.status_code == 422
    assert epoch.status_code == 422
    assert good.status_code == 200


def test_web_api_recall_respects_requester_acl(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    private = client.post(
        "/api/memories", json={"content": "Private note.", "owner": "mizuki", "visibility": []}
    ).json()

    response = client.post(
        "/api/recall",
        json={"memory_ids": [private["id"]], "helpful": False, "requester_agent_id": "neo"},
    )

    assert response.status_code == 200
    assert response.json()["weakened_memories"] == 0
    fetched = client.get(f"/api/memories/{private['id']}").json()
    assert fetched["confidence"] == 0.8


def test_web_api_list_memories_respects_requester_acl(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    client.post("/api/memories", json={"content": "Private one.", "owner": "mizuki", "visibility": []})
    client.post("/api/memories", json={"content": "Public one.", "owner": "mizuki", "visibility": ["global"]})

    admin_view = client.get("/api/memories").json()["memories"]
    neo_view = client.get("/api/memories", params={"requester_agent_id": "neo"}).json()["memories"]

    assert len(admin_view) == 2
    assert [m["content"] for m in neo_view] == ["Public one."]


def test_web_api_delete_memory(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    created = client.post(
        "/api/memories", json={"content": "Disposable.", "visibility": ["global"]}
    ).json()

    assert client.delete(f"/api/memories/{created['id']}").status_code == 200
    assert client.get(f"/api/memories/{created['id']}").status_code == 404
    assert client.delete(f"/api/memories/{created['id']}").status_code == 404


def test_web_api_graph_is_requester_gated(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    public_a = client.post(
        "/api/memories", json={"content": "Public deploy checklist.", "owner": "mizuki", "visibility": ["global"]}
    ).json()
    private = client.post(
        "/api/memories", json={"content": "Private reflection.", "owner": "mizuki", "visibility": []}
    ).json()
    public_b = client.post(
        "/api/memories", json={"content": "Public retro notes.", "owner": "mizuki", "visibility": ["global"]}
    ).json()
    client.post("/api/links", json={"src_id": public_a["id"], "dst_id": private["id"]})
    client.post("/api/links", json={"src_id": public_a["id"], "dst_id": public_b["id"]})

    admin = client.get("/api/graph").json()
    neo = client.get("/api/graph", params={"requester_agent_id": "neo"}).json()

    assert len(admin["nodes"]) == 3 and len(admin["edges"]) == 2
    neo_ids = {node["id"] for node in neo["nodes"]}
    assert private["id"] not in neo_ids
    assert len(neo["edges"]) == 1
    assert all(edge["src"] in neo_ids and edge["dst"] in neo_ids for edge in neo["edges"])


def test_web_api_list_type_filter(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    client.post("/api/memories", json={"content": "A procedure.", "type": "procedure", "visibility": ["global"]})
    client.post("/api/memories", json={"content": "A note.", "type": "note", "visibility": ["global"]})

    filtered = client.get("/api/memories", params={"type": "procedure"}).json()["memories"]

    assert [m["content"] for m in filtered] == ["A procedure."]


def test_web_api_token_gate(tmp_path):
    app = create_app(home=tmp_path, token="s3cret")
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/stats", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_web_api_update_memory_and_reindex(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    created = client.post(
        "/api/memories", json={"content": "Original zebra content.", "visibility": ["global"]}
    ).json()

    updated = client.patch(
        f"/api/memories/{created['id']}",
        json={"content": "Updated flamingo content.", "importance": 0.9, "pinned": True,
              "tags": ["updated"], "type": "fact"},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["content"] == "Updated flamingo content."
    assert payload["pinned"] is True
    assert payload["type"] == "fact"
    assert payload["tags"] == ["updated"]

    # FTS reindexed: the old term no longer matches lexically (any results are
    # the zero-hit fallback safety net, never an fts hit)
    zebra_hits = client.get("/api/search", params={"q": "zebra"}).json()["results"]
    assert all(hit["reason"].startswith("fallback") for hit in zebra_hits)
    hits = client.get("/api/search", params={"q": "flamingo"}).json()["results"]
    assert hits and hits[0]["id"] == created["id"]

    assert client.patch("/api/memories/mem_missing", json={"content": "x"}).status_code == 404
    assert client.patch(f"/api/memories/{created['id']}", json={}).status_code == 400
    assert client.patch(
        f"/api/memories/{created['id']}", json={"scope": "kingdom"}
    ).status_code == 422


def test_web_api_dashboard(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    a = client.post(
        "/api/memories",
        json={"content": "Pinned deploy fact.", "scope": "project", "type": "fact",
              "visibility": ["global"], "pinned": True},
    ).json()
    b = client.post(
        "/api/memories", json={"content": "A note.", "visibility": ["global"]}
    ).json()
    client.post("/api/links", json={"src_id": a["id"], "dst_id": b["id"], "relation": "caused_by"})
    client.post("/api/recall", json={"memory_ids": [a["id"]]})

    data = client.get("/api/dashboard").json()

    assert data["total"] == 2
    assert data["pinned"] == 1
    assert data["links"] == 1
    assert data["by_relation"] == {"caused_by": 1}
    assert data["by_scope"]["project"] == 1
    assert len(data["activity"]) == 14
    assert data["activity"][-1]["count"] == 2
    assert data["top_recalled"][0]["id"] == a["id"]


def test_web_api_purge_owner_requires_exact_confirmation(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    kept = client.post(
        "/api/memories", json={"content": "Neo memory stays.", "owner": "neo", "visibility": ["global"]}
    ).json()
    doomed_a = client.post(
        "/api/memories", json={"content": "Mizuki memory one.", "owner": "mizuki", "visibility": ["global"]}
    ).json()
    doomed_b = client.post(
        "/api/memories", json={"content": "Mizuki memory two.", "owner": "mizuki", "visibility": []}
    ).json()
    client.post("/api/links", json={"src_id": doomed_a["id"], "dst_id": kept["id"]})
    client.post("/api/links", json={"src_id": doomed_a["id"], "dst_id": doomed_b["id"]})

    # No / wrong confirmation → refused, nothing deleted
    assert client.delete("/api/owners/mizuki/memories").status_code == 400
    assert client.delete("/api/owners/mizuki/memories", params={"confirm": "MIZUKI"}).status_code == 400
    assert client.get("/api/stats").json()["total"] == 3

    response = client.delete("/api/owners/mizuki/memories", params={"confirm": "mizuki"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["memories_deleted"] == 2
    assert payload["links_deleted"] == 2
    stats = client.get("/api/stats").json()
    assert stats["total"] == 1 and stats["links"] == 0
    assert client.get(f"/api/memories/{kept['id']}").status_code == 200
    assert client.get(f"/api/memories/{doomed_a['id']}").status_code == 404


def test_webui_toplevel_handlers_reference_existing_ids():
    """Guard against the class of bug where a top-level $("id").addEventListener
    targets an element that isn't in the HTML — one such orphan throws at script
    load and takes down the ENTIRE dashboard (version badge, counts, cards,
    browse). Every id wired at the top level must exist in the page markup.
    """
    import re

    from agent_memory_os.web_ui import PAGE

    handler_ids = set(re.findall(r'\$\("([a-zA-Z][\w-]+)"\)\.addEventListener', PAGE))
    assert handler_ids, "expected some top-level handlers"
    present_ids = set(re.findall(r'id="([\w-]+)"', PAGE))
    missing = sorted(handler_ids - present_ids)
    assert not missing, f"handlers reference ids with no HTML element: {missing}"


def test_web_api_owners_list_and_reassign(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)

    for owner in ("default", "default", "mizuki"):
        client.post("/api/memories", json={"content": f"n {owner}", "owner": owner})

    owners = client.get("/api/owners").json()["owners"]
    counts = {o["owner"]: o for o in owners}
    assert counts["default"]["memories"] == 2
    assert counts["mizuki"]["memories"] == 1

    r = client.post("/api/owners/reassign",
                    json={"old_owner": "default", "new_owner": "mizuki"})
    assert r.status_code == 200
    assert r.json()["changed"]["memories_owner"] == 2

    owners2 = {o["owner"]: o for o in client.get("/api/owners").json()["owners"]}
    assert "default" not in owners2
    assert owners2["mizuki"]["memories"] == 3


def test_web_api_owners_reassign_rejects_identical(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    r = client.post("/api/owners/reassign", json={"old_owner": "x", "new_owner": "x"})
    assert r.status_code == 400


def test_web_api_peers_status_probes_and_reports(tmp_path):
    app = create_app(home=tmp_path)
    client = TestClient(app)
    # No peers → empty, fast.
    assert client.get("/api/peers/status").json() == {"statuses": []}
    # A registered but unreachable peer reports reachable=False with keys the
    # console's color dot relies on.
    client.post("/api/peers", json={"url": "http://127.0.0.1:9", "policy": "shared"})
    statuses = client.get("/api/peers/status").json()["statuses"]
    assert len(statuses) == 1
    s = statuses[0]
    assert s["url"] == "http://127.0.0.1:9"
    assert s["reachable"] is False
    for key in ("name", "node_name", "is_amos", "status", "integrity", "version", "detail"):
        assert key in s
