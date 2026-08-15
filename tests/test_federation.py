import json

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app

BACKDATED = "2020-01-01T00:00:00.000000Z"


# ---------- cross-agent memory negotiation ----------


def test_share_grants_visibility_only_by_owner_with_audit(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    memory = client.add("Mizuki private planning note.", owner="mizuki", visibility=[])

    # negotiation boundary: only the owner may share
    with pytest.raises(PermissionError):
        client.share_memory(memory.id, actor="neo", to_agent="neo")
    assert client.search("planning note", requester_agent_id="neo") == []

    result = client.share_memory(memory.id, actor="mizuki", to_agent="neo")
    assert result == {"shared_as": memory.id, "grant": "agent:neo", "deidentified": False}
    hits = client.search("planning note", requester_agent_id="neo")
    assert [hit.record.id for hit in hits] == [memory.id]

    client.revoke_share(memory.id, actor="mizuki", to_agent="neo")
    assert client.search("planning note", requester_agent_id="neo") == []

    actions = [(entry["actor"], entry["action"], entry["detail"]) for entry in client.audit_log(memory.id)]
    assert ("mizuki", "share", "agent:neo") in actions
    assert ("mizuki", "revoke", "agent:neo") in actions


def test_deidentified_share_scrubs_owner_and_keeps_original_private(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    memory = client.add(
        "mizuki prefers dark mode and mizuki reviews at night.",
        owner="mizuki", type="preference", visibility=[],
    )

    result = client.share_memory(
        memory.id, actor="mizuki", to_team="core", deidentify=True
    )

    assert result["deidentified"] is True and result["shared_as"] != memory.id
    copy = client.get(result["shared_as"])
    assert "mizuki" not in copy.content
    assert "a teammate" in copy.content
    assert copy.visibility == ["team:core"]
    assert copy.source == {"shared": "deidentified"}
    # original untouched and still private
    assert client.get(memory.id).visibility == []
    # provenance lives in the audit trail, not in the copy
    assert any(e["action"] == "share_deidentified" for e in client.audit_log(memory.id))
    assert any(e["action"] == "created_from_share" for e in client.audit_log(copy.id))


def test_web_api_share_enforces_owner(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6.
    """
    app = create_app(home=tmp_path)
    web = TestClient(app)
    memory = web.post(
        "/api/memories", json={"content": "Private plan.", "owner": "mizuki", "visibility": []}
    ).json()

    forbidden = web.post(
        f"/api/memories/{memory['id']}/share", json={"actor": "neo", "to_agent": "neo"}
    )
    assert forbidden.status_code == 403

    ok = web.post(
        f"/api/memories/{memory['id']}/share", json={"actor": "mizuki", "to_agent": "neo"}
    )
    assert ok.status_code == 200 and ok.json()["grant"] == "agent:neo"
    audit = web.get(f"/api/memories/{memory['id']}/audit").json()["audit"]
    assert audit and audit[-1]["action"] == "share"


# ---------- federated bundle sync ----------


def test_bundle_roundtrip_with_last_writer_wins(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6; 06cb42f7@db-schema-v9.
    """
    host_a = MemoryClient(home=tmp_path / "a")
    host_b = MemoryClient(home=tmp_path / "b")

    shared = host_a.add("Deploy target is port 8000.", visibility=["global"])
    other = host_a.add("Rollback snapshot rule.", visibility=["global"])
    host_a.link(shared.id, other.id, relation="caused_by", weight=0.7)
    # second-resolution timestamps: backdate A's rows so B's later edit is
    # strictly newer for the conflict-resolution assertions below
    host_a.store.conn.execute("UPDATE memories SET updated_at = ?", (BACKDATED,))
    host_a.store.conn.commit()
    from agent_memory_os import RecallProfile
    host_a.save_profile(RecallProfile(agent_id="neo", type_weights={"procedure": 1.5}))

    bundle = tmp_path / "bundle.jsonl"
    exported = host_a.export_bundle(bundle)
    assert exported == {"memories": 2, "links": 1, "profiles": 1, "tombstones": 0}

    stats = host_b.import_bundle(bundle)
    assert stats["memories_added"] == 2 and stats["links_added"] == 1
    assert stats["profiles_upserted"] == 1
    assert host_b.get(shared.id).content == "Deploy target is port 8000."
    assert host_b.links(shared.id)[0].relation == "caused_by"

    # conflict: B edits (newer updated_at) then re-imports A's bundle → B wins
    host_b.update(shared.id, content="Deploy target is port 9000.")
    stats = host_b.import_bundle(bundle)
    assert stats["memories_skipped"] >= 1
    assert host_b.get(shared.id).content == "Deploy target is port 9000."

    # reverse direction: export B, import into A → A receives the newer edit
    reverse = tmp_path / "reverse.jsonl"
    host_b.export_bundle(reverse)
    stats = host_a.import_bundle(reverse)
    assert stats["memories_updated"] == 1
    assert host_a.get(shared.id).content == "Deploy target is port 9000."
    host_a.close(); host_b.close()


def test_v4_bundle_link_insert_preserves_last_activation_stamp(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    host_a = MemoryClient(home=tmp_path / "a")
    host_b = MemoryClient(home=tmp_path / "b")
    source = host_a.add("Source memory.", visibility=["global"])
    target = host_a.add("Target memory.", visibility=["global"])
    host_a.link(source.id, target.id, weight=0.7)
    host_a.store.conn.execute(
        "UPDATE memory_links SET last_activated_at = ?, activation_count = 1",
        ("2026-08-10T13:00:00.000000Z",),
    )
    host_a.store.conn.commit()

    bundle = tmp_path / "link-insert.jsonl"
    host_a.export_bundle(bundle)
    stats = host_b.import_bundle(bundle)

    assert stats["links_added"] == 1
    link = host_b.links(source.id)[0]
    assert link.last_activated_at == "2026-08-10T13:00:00.000000Z"
    host_a.close(); host_b.close()


def test_bundle_link_merge_uses_activation_instant_and_canonical_storage(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 22a21d81@db-schema-v21; working-tree@db-schema-v22.
    """
    host_a = MemoryClient(home=tmp_path / "a")
    host_b = MemoryClient(home=tmp_path / "b")
    source = host_a.add("Source memory.", visibility=["global"])
    target = host_a.add("Target memory.", visibility=["global"])
    host_a.link(source.id, target.id, weight=0.5)

    bundle = tmp_path / "link-conflict.jsonl"
    host_a.export_bundle(bundle)
    host_b.import_bundle(bundle)
    host_b.store.conn.execute(
        "UPDATE memory_links SET weight = ?, activation_count = ?, last_activated_at = ?",
        (0.4, 3, "2026-08-10T12:30:00.000000Z"),
    )
    host_b.store.conn.commit()

    host_a.store.conn.execute(
        "UPDATE memory_links SET weight = ?, activation_count = ?, last_activated_at = ?",
        (0.9, 2, "2026-08-10T12:00:00.000000Z"),
    )
    host_a.store.conn.commit()
    host_a.export_bundle(bundle)
    stats = host_b.import_bundle(bundle)
    link = host_b.links(source.id)[0]

    assert stats["links_merged"] == 1
    assert link.weight == 0.9
    assert link.activation_count == 3
    assert link.last_activated_at == "2026-08-10T12:30:00.000000Z"

    host_a.store.conn.execute(
        "UPDATE memory_links SET last_activated_at = ?",
        ("2026-08-10T13:00:00.000000Z",),
    )
    host_a.store.conn.commit()
    host_a.export_bundle(bundle)
    stats = host_b.import_bundle(bundle)

    assert stats["links_merged"] == 1
    assert host_b.links(source.id)[0].last_activated_at == "2026-08-10T13:00:00.000000Z"
    host_a.close(); host_b.close()


def test_bundle_link_merge_preserves_absent_activation_timestamp(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 22a21d81@db-schema-v21.
    """
    host_a = MemoryClient(home=tmp_path / "a")
    host_b = MemoryClient(home=tmp_path / "b")
    source = host_a.add("Source memory.", visibility=["global"])
    target = host_a.add("Target memory.", visibility=["global"])
    host_a.link(source.id, target.id, weight=0.5)

    bundle = tmp_path / "link-null.jsonl"
    host_a.export_bundle(bundle)
    host_b.import_bundle(bundle)
    stats = host_b.import_bundle(bundle)

    assert stats["links_merged"] == 1
    assert host_b.links(source.id)[0].last_activated_at is None
    host_a.close(); host_b.close()


def test_incremental_export_uses_stamp_since_for_all_timestamp_cursors(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    client = MemoryClient(home=tmp_path / "home")
    source = client.add("Source memory.", visibility=["global"])
    target = client.add("ACL-fresh target memory.", visibility=["global"])
    client.link(source.id, target.id, weight=0.7)
    client.store.create_team("apollo")
    client.store.create_project("landing", "apollo")

    newer = "2026-08-10T12:30:00.000000Z"
    older = "2026-08-10T11:30:00.000000Z"
    client.store.conn.execute(
        "UPDATE memories SET updated_at = ?, acl_updated_at = ? WHERE id = ?",
        (newer, newer, source.id),
    )
    client.store.conn.execute(
        "UPDATE memories SET updated_at = ?, acl_updated_at = ? WHERE id = ?",
        (older, newer, target.id),
    )
    client.store.conn.execute("UPDATE memory_links SET updated_at = ?", (newer,))
    client.store.conn.execute("UPDATE teams SET updated_at = ?", (newer,))
    client.store.conn.execute("UPDATE projects SET updated_at = ?", (newer,))
    client.store.conn.execute(
        "INSERT INTO tombstones(id, deleted_at) VALUES (?, ?)",
        ("deleted-memory", newer),
    )
    client.store.conn.execute(
        "INSERT INTO org_tombstones(kind, id, deleted_at) VALUES (?, ?, ?)",
        ("project", "deleted-project", newer),
    )
    client.store.conn.commit()

    zulu_bundle = tmp_path / "zulu.jsonl"
    zulu_counts = client.export_bundle(
        zulu_bundle,
        since="2026-08-10T12:00:00.000000Z",
    )

    assert zulu_counts == {
        "memories": 2,
        "links": 1,
        "profiles": 0,
        "tombstones": 1,
    }
    zulu_entries = [json.loads(line) for line in zulu_bundle.read_text().splitlines()]
    assert {entry["kind"] for entry in zulu_entries} == {
        "bundle", "memory", "link", "tombstone", "team", "project", "org_tombstone",
    }
    with pytest.raises(ValueError, match="timestamp must match"):
        client.export_bundle(
            tmp_path / "offset.jsonl",
            since="2026-08-10T13:00:00+01:00",
        )
    client.close()


def test_incremental_export_keeps_fresh_link_with_unchanged_endpoints(tmp_path):
    source_client = MemoryClient(home=tmp_path / "source")
    relay_client = MemoryClient(home=tmp_path / "relay")
    source = source_client.add("Old source.", visibility=["global"])
    target = source_client.add("Old target.", visibility=["global"])
    source_client.link(source.id, target.id, weight=0.2)
    source_client.store.conn.execute(
        "UPDATE memories SET updated_at = ?, acl_updated_at = ?",
        ("2026-08-10T11:00:00.000000Z", "2026-08-10T11:00:00.000000Z"),
    )
    source_client.store.conn.execute(
        "UPDATE memory_links SET updated_at = ?",
        ("2026-08-10T11:00:00.000000Z",),
    )
    source_client.store.conn.commit()

    seed = tmp_path / "seed.jsonl"
    source_client.export_bundle(seed)
    relay_client.import_bundle(seed)

    source_client.store.conn.execute(
        "UPDATE memory_links SET weight = ?, updated_at = ?",
        (0.9, "2026-08-10T13:00:00.000000Z"),
    )
    source_client.store.conn.commit()
    incremental = tmp_path / "incremental.jsonl"
    counts = source_client.export_bundle(
        incremental,
        since="2026-08-10T12:00:00.000000Z",
    )

    assert counts["memories"] == 0
    assert counts["links"] == 1
    merged = relay_client.import_bundle(incremental)
    assert merged["links_merged"] == 1
    assert relay_client.links(source.id)[0].weight == 0.9
    source_client.close()
    relay_client.close()


def test_incremental_export_filters_profiles_by_their_updated_stamp(tmp_path):
    """Execution contract: current schema v22 and bundle contract v4.

    Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    from agent_memory_os import RecallProfile

    client = MemoryClient(home=tmp_path / "home")
    client.save_profile(RecallProfile(agent_id="old"))
    client.save_profile(RecallProfile(agent_id="new"))
    client.store.conn.execute(
        "UPDATE recall_profiles SET updated_at = ? WHERE agent_id = ?",
        ("2026-08-10T11:00:00.000000Z", "old"),
    )
    client.store.conn.execute(
        "UPDATE recall_profiles SET updated_at = ? WHERE agent_id = ?",
        ("2026-08-10T13:00:00.000000Z", "new"),
    )
    client.store.conn.commit()

    bundle = tmp_path / "profiles.jsonl"
    counts = client.export_bundle(
        bundle,
        since="2026-08-10T12:00:00.000000Z",
    )
    entries = [json.loads(line) for line in bundle.read_text().splitlines()]

    assert counts["profiles"] == 1
    assert [
        entry["agent_id"] for entry in entries if entry["kind"] == "profile"
    ] == ["new"]
    client.close()


@pytest.mark.parametrize("scope_kind", ["team", "project"])
def test_incremental_scoped_export_includes_profile_newly_eligible_by_membership(
    tmp_path,
    scope_kind,
):
    from agent_memory_os import RecallProfile

    client = MemoryClient(home=tmp_path / scope_kind)
    client.store.register_agent("alice")
    client.save_profile(RecallProfile(agent_id="alice"))
    client.store.create_team("eng")
    client.store.add_team_member("eng", "alice")
    export_kwargs = {"team": "eng"}
    scope_table = "teams"
    scope_id = "eng"
    if scope_kind == "project":
        client.store.create_project("proj", "eng")
        client.store.add_project_member("proj", "alice")
        export_kwargs = {"project": "proj"}
        scope_table = "projects"
        scope_id = "proj"

    client.store.conn.execute(
        "UPDATE recall_profiles SET updated_at = ? WHERE agent_id = ?",
        ("2026-08-10T11:00:00.000000Z", "alice"),
    )
    client.store.conn.execute(
        f"UPDATE {scope_table} SET updated_at = ? WHERE id = ?",
        ("2026-08-10T13:00:00.000000Z", scope_id),
    )
    client.store.conn.commit()

    bundle = tmp_path / f"{scope_kind}-profiles.jsonl"
    counts = client.export_bundle(
        bundle,
        since="2026-08-10T12:00:00.000000Z",
        **export_kwargs,
    )
    profiles = [
        entry["agent_id"]
        for entry in map(json.loads, bundle.read_text().splitlines())
        if entry["kind"] == "profile"
    ]

    assert counts["profiles"] == 1
    assert profiles == ["alice"]
    client.close()


def test_merged_link_advances_its_clock_for_incremental_onward_export(tmp_path):
    """Execution contract: current schema v22 and bundle contract v4.

    Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    source_client = MemoryClient(home=tmp_path / "source")
    relay_client = MemoryClient(home=tmp_path / "relay")
    source = source_client.add("Source memory.", visibility=["global"])
    target = source_client.add("Target memory.", visibility=["global"])
    source_client.link(source.id, target.id, weight=0.2)
    source_client.store.conn.execute(
        "UPDATE memory_links SET updated_at = ?, last_activated_at = NULL, "
        "activation_count = 0",
        ("2026-08-10T11:00:00.000000Z",),
    )
    source_client.store.conn.commit()

    seed = tmp_path / "seed.jsonl"
    source_client.export_bundle(seed)
    relay_client.import_bundle(seed)

    source_client.store.conn.execute(
        "UPDATE memory_links SET weight = ?, updated_at = ?, "
        "last_activated_at = ?, activation_count = ?",
        (
            0.9,
            "2026-08-10T13:00:00.000000Z",
            "2026-08-10T13:00:00.000000Z",
            2,
        ),
    )
    source_client.store.conn.commit()
    update = tmp_path / "update.jsonl"
    source_client.export_bundle(update)
    relay_client.import_bundle(update)

    merged = relay_client.store.conn.execute(
        "SELECT weight, updated_at, last_activated_at, activation_count "
        "FROM memory_links"
    ).fetchone()
    assert tuple(merged) == (
        0.9,
        "2026-08-10T13:00:00.000000Z",
        "2026-08-10T13:00:00.000000Z",
        2,
    )

    onward = tmp_path / "onward.jsonl"
    counts = relay_client.export_bundle(
        onward,
        since="2026-08-10T12:00:00.000000Z",
    )
    assert counts["links"] == 1
    source_client.close()
    relay_client.close()


def test_v3_bundle_import_converts_timestamps_for_every_record_kind(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    source_client = MemoryClient(home=tmp_path / "source")
    target_client = MemoryClient(home=tmp_path / "target")
    source = source_client.add("Source memory.", visibility=["global"])
    target = source_client.add("Target memory.", visibility=["global"])
    source_client.link(source.id, target.id, weight=0.7)
    source_client.store.create_team("apollo")
    source_client.store.create_project("landing", "apollo")
    from agent_memory_os import RecallProfile
    source_client.save_profile(RecallProfile(agent_id="neo"))
    source_client.store.conn.execute(
        "INSERT INTO tombstones(id, deleted_at) VALUES (?, ?)",
        ("deleted-memory", "2026-08-10T13:00:00.000000Z"),
    )
    source_client.store.conn.execute(
        "INSERT INTO org_tombstones(kind, id, deleted_at) VALUES (?, ?, ?)",
        ("project", "deleted-project", "2026-08-10T13:00:00.000000Z"),
    )
    source_client.store.conn.commit()

    bundle = tmp_path / "all-kinds.jsonl"
    source_client.export_bundle(bundle)
    entries = [json.loads(line) for line in bundle.read_text().splitlines()]
    entries[0]["version"] = 3
    timestamp_fields = {
        "memory": (
            "created_at", "updated_at", "acl_updated_at", "expires_at", "last_accessed_at",
        ),
        "link": ("created_at", "updated_at", "last_activated_at"),
        "profile": ("updated_at",),
        "tombstone": ("deleted_at",),
        "team": ("updated_at",),
        "project": ("updated_at",),
        "org_tombstone": ("deleted_at",),
    }
    offset_timestamp = "2026-08-10T14:00:00+01:00"
    for entry in entries:
        for field in timestamp_fields.get(entry["kind"], ()):
            entry[field] = offset_timestamp
    bundle.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    target_client.import_bundle(bundle)
    canonical = "2026-08-10T13:00:00.000000Z"
    persisted = []
    for row in target_client.store.conn.execute(
        "SELECT created_at, updated_at, acl_updated_at, expires_at, last_accessed_at FROM memories"
    ):
        persisted.extend(row)
    persisted.extend(target_client.store.conn.execute(
        "SELECT created_at, updated_at, last_activated_at FROM memory_links"
    ).fetchone())
    persisted.append(target_client.store.conn.execute(
        "SELECT updated_at FROM recall_profiles"
    ).fetchone()[0])
    persisted.append(target_client.store.conn.execute(
        "SELECT deleted_at FROM tombstones"
    ).fetchone()[0])
    persisted.extend(target_client.store.conn.execute(
        "SELECT created_at, updated_at FROM teams"
    ).fetchone())
    persisted.extend(target_client.store.conn.execute(
        "SELECT created_at, updated_at FROM projects"
    ).fetchone())
    persisted.append(target_client.store.conn.execute(
        "SELECT deleted_at FROM org_tombstones"
    ).fetchone()[0])

    assert persisted
    assert set(persisted) == {canonical}
    source_client.close(); target_client.close()


def test_bundle_import_rejects_malformed_expiry_without_persisting_it(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 03883e92@db-schema-v21; working-tree@db-schema-v22.
    """
    source_client = MemoryClient(home=tmp_path / "source")
    target_client = MemoryClient(home=tmp_path / "target")
    memory = source_client.add("Malformed expiry source.", visibility=["global"])
    bundle = tmp_path / "malformed-expiry.jsonl"
    source_client.export_bundle(bundle)
    entries = [json.loads(line) for line in bundle.read_text().splitlines()]
    next(entry for entry in entries if entry["kind"] == "memory")["expires_at"] = "not-a-time"
    bundle.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="bundle v4 memory.expires_at must be a canonical stamp",
    ):
        target_client.import_bundle(bundle)
    assert target_client.get(memory.id) is None
    source_client.close(); target_client.close()


def test_bundle_import_rejects_foreign_files(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    bogus = tmp_path / "bogus.jsonl"
    bogus.write_text('{"kind": "something-else"}\n')
    with pytest.raises(ValueError):
        client.import_bundle(bogus)


# ---------- telemetry-tuned forgetting curves ----------


def test_feedback_telemetry_tunes_half_lives(tmp_path):
    """Lineage:
    main: introduced 512e2197@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    trusted = client.add("Helpful fact.", type="fact", visibility=["global"])   # base 90d
    misleading = client.add("Misleading fact.", type="fact", visibility=["global"])
    untouched = client.add("Untouched fact.", type="fact", visibility=["global"])

    for _ in range(8):
        client.record_recall([trusted.id], helpful=True)
    for _ in range(8):
        client.record_recall([misleading.id], helpful=False)

    result = client.run_retention()
    assert result["tuned_half_lives"] == 2

    tuned_up = client.get(trusted.id).decay_half_life_days
    tuned_down = client.get(misleading.id).decay_half_life_days
    assert tuned_up == 270.0            # 90 * sqrt(9/1) = 270 → helpful forgets slower
    assert tuned_down == 45.0           # 90 * clamp(sqrt(1/9), 0.5) → misleading forgets faster
    assert client.get(untouched.id).decay_half_life_days == 90.0

    # idempotent: rerunning without new feedback changes nothing
    assert client.run_retention()["tuned_half_lives"] == 0


# ---------- peer HTTP sync transport ----------


def test_sync_http_endpoints_move_memories_between_hosts(tmp_path):
    """Lineage:
    main: introduced 55aa3fe4@db-schema-v6.
    """
    host_a = TestClient(create_app(home=tmp_path / "a"))
    host_b = TestClient(create_app(home=tmp_path / "b"))
    created = host_a.post(
        "/api/memories", json={"content": "Peer-synced memory.", "visibility": ["global"]}
    ).json()

    bundle = host_a.get("/api/sync/export")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"].startswith("application/x-ndjson")

    merged = host_b.post(
        "/api/sync/import", content=bundle.text,
        headers={"content-type": "application/x-ndjson"},
    )
    assert merged.status_code == 200
    assert merged.json()["memories_added"] == 1
    assert host_b.get(f"/api/memories/{created['id']}").status_code == 200

    # importing garbage is rejected
    bad = host_b.post("/api/sync/import", content='{"kind": "nope"}\n')
    assert bad.status_code == 400


def test_sync_export_rejects_noncanonical_since(tmp_path):
    web = TestClient(
        create_app(home=tmp_path),
        raise_server_exceptions=False,
    )

    canonical = web.get(
        "/api/sync/export",
        params={"since": "2026-08-10T12:00:00.000000Z"},
    )
    assert canonical.status_code == 200

    for invalid in ("not-a-stamp", "2026-08-10T13:00:00+01:00"):
        response = web.get("/api/sync/export", params={"since": invalid})
        assert response.status_code == 400


def test_sync_endpoints_respect_token_gate(tmp_path):
    """Lineage:
    main: introduced 55aa3fe4@db-schema-v6.
    """
    app = create_app(home=tmp_path, token="s3cret")
    web = TestClient(app)

    assert web.get("/api/sync/export").status_code == 401
    assert web.get(
        "/api/sync/export", headers={"Authorization": "Bearer s3cret"}
    ).status_code == 200


# ---------- pluggable link extraction at consolidation ----------


def test_consolidate_derive_links_uses_era_heuristic(tmp_path):
    """Lineage:
    main: introduced 55aa3fe4@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    a = client.add("AgentMemoryOS uses Turbovec for semantic recall.", visibility=["global"])
    b = client.add("Turbovec semantic recall benchmark notes.", visibility=["global"])
    client.add("Cooking pasta with garlic tonight.", visibility=["global"])

    result = client.consolidate(derive_links=True)

    assert result["links_derived"] >= 1
    assert any({link.src_id, link.dst_id} == {a.id, b.id} for link in client.links(a.id))
    # derived edges are marked and idempotent (existing pairs skipped)
    assert client.links(a.id)[0].source == {"auto": "consolidation_extractor"}
    assert client.consolidate(derive_links=True)["links_derived"] == 0


def test_consolidate_accepts_custom_link_extractor(tmp_path):
    """Lineage:
    main: introduced 55aa3fe4@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    a = client.add("Alpha memory.", visibility=["global"])
    b = client.add("Beta memory.", visibility=["global"])

    def llm_like_extractor(records):
        ids = [record.id for record in records]
        assert a.id in ids and b.id in ids
        return [(a.id, b.id, 0.9)]

    result = client.consolidate(link_extractor=llm_like_extractor)

    assert result["links_derived"] == 1
    assert client.links(a.id)[0].weight == 0.9


# ---------- peer registry & mesh auto-sync ----------


def test_peer_registry_and_mesh_sync(tmp_path, monkeypatch):
    """Lineage:
    main: introduced bedbc1c0@db-schema-v7.
    """
    host_a = MemoryClient(home=tmp_path / "a")
    peer_app = TestClient(create_app(home=tmp_path / "b"))
    created = peer_app.post(
        "/api/memories", json={"content": "Memory living on peer B.", "visibility": ["global"]}
    ).json()

    # registry CRUD + validation
    import pytest as _pytest
    with _pytest.raises(ValueError):
        host_a.store.add_peer("ftp://nope")
    host_a.store.add_peer("http://peer-b:8000/", token="s3cret")
    peers = host_a.store.list_peers()
    assert peers[0]["url"] == "http://peer-b:8000" and peers[0]["has_token"] is True

    # route the mesh's HTTP through the in-process peer app
    from agent_memory_os import sync as sync_module

    def fake_http(url, *, token, post=None):
        assert token == "s3cret"  # registered token is used
        path = url.replace("http://peer-b:8000", "")
        if post is None:
            return peer_app.get(path).text
        response = peer_app.post(path, content=post, headers={"content-type": "application/x-ndjson"})
        return response.text

    monkeypatch.setattr(sync_module, "_http", fake_http)

    local_memory = host_a.add("Memory living on host A.", visibility=["global"])
    results = sync_module.sync_all_peers(host_a)

    assert results[0]["ok"] is True
    # pulled B's memory, pushed A's memory
    assert host_a.get(created["id"]) is not None
    assert peer_app.get(f"/api/memories/{local_memory.id}").status_code == 200
    # sync outcome recorded on the peer row
    assert host_a.store.list_peers()[0]["last_result"].startswith("ok")

    # unreachable peers fail per-peer, not fatally
    host_a.store.add_peer("http://unreachable:1")
    results = sync_module.sync_all_peers(host_a)
    assert any(r["ok"] is False for r in results) and any(r["ok"] is True for r in results)

    assert host_a.store.remove_peer("http://unreachable:1") is True
    host_a.close()


def test_sync_all_peers_reports_http_error_response_detail(tmp_path, monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from agent_memory_os import sync as sync_module

    client = MemoryClient(home=tmp_path)
    peer_url = "http://peer:8000"
    client.store.add_peer(peer_url)
    detail = "since timestamp must match canonical UTC stamp"

    def reject_request(*args, **kwargs):
        raise urllib.error.HTTPError(
            peer_url,
            400,
            "Bad Request",
            None,
            io.BytesIO(json.dumps({"detail": detail}).encode("utf-8")),
        )

    monkeypatch.setattr(urllib.request, "urlopen", reject_request)
    result = sync_module.sync_all_peers(client)[0]

    assert result["ok"] is False
    assert detail in result["error"]
    assert detail in client.store.list_peers()[0]["last_result"]
    client.close()


def test_web_api_peers_endpoints(tmp_path):
    """Lineage:
    main: introduced bedbc1c0@db-schema-v7.
    """
    web = TestClient(create_app(home=tmp_path))

    assert web.post("/api/peers", json={"url": "http://peer:8000"}).status_code == 200
    listed = web.get("/api/peers").json()["peers"]
    assert listed[0]["url"] == "http://peer:8000"
    assert web.post("/api/peers", json={"url": "gopher://x"}).status_code == 400
    assert web.delete("/api/peers", params={"url": "http://peer:8000"}).status_code == 200
    assert web.delete("/api/peers", params={"url": "http://peer:8000"}).status_code == 404


# ---------- LLM link extractor helper ----------


def test_llm_link_extractor_parses_and_guards(tmp_path):
    """Lineage:
    main: introduced bedbc1c0@db-schema-v7.
    """
    from agent_memory_os.extractors import make_llm_link_extractor

    client = MemoryClient(home=tmp_path)
    a = client.add("Deploy procedure for staging.", visibility=["global"])
    b = client.add("Staging deploy failed last week.", visibility=["global"])
    c = client.add("Banana bread recipe.", visibility=["global"])

    prompts = []

    def fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        return (
            "Here you go:\n"
            f'[{{"src": "{a.id}", "dst": "{b.id}", "weight": 0.8}},'
            f' {{"src": "{a.id}", "dst": "{b.id}", "weight": 0.8}},'   # dup dropped
            f' {{"src": "{a.id}", "dst": "{a.id}"}},'                  # self dropped
            f' {{"src": "{a.id}", "dst": "mem_unknown"}},'             # unknown dropped
            f' {{"src": "{c.id}", "dst": "{b.id}", "weight": 9}}]'     # weight clamped
        )

    result = client.consolidate(link_extractor=make_llm_link_extractor(fake_llm))

    assert result["links_derived"] == 2
    assert a.id in prompts[0] and "JSON array" in prompts[0]
    weights = {frozenset((l.src_id, l.dst_id)): l.weight for l in client.links(b.id)}
    assert weights[frozenset((a.id, b.id))] == 0.8
    assert weights[frozenset((c.id, b.id))] == 1.0  # clamped

    # garbage output degrades to zero links, never raises
    broken = make_llm_link_extractor(lambda prompt: "sorry, no JSON here")
    assert client.consolidate(link_extractor=broken)["links_derived"] == 0
