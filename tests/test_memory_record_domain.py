from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_memory_os.client import MemoryClient


@pytest.mark.parametrize("scope", ["", "workspace", "USER"])
def test_sdk_rejects_unknown_memory_scope(tmp_path, scope):
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match="scope must be one of"):
        client.add("Invalid scope record.", scope=scope)


@pytest.mark.parametrize("memory_type", ["", "snapshot-ish", "FACT"])
def test_sdk_rejects_unknown_memory_type(tmp_path, memory_type):
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match="type must be one of"):
        client.add("Invalid type record.", type=memory_type)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("confidence", "high"),
        ("importance", -0.01),
        ("importance", 1.01),
        ("importance", True),
    ],
)
def test_sdk_rejects_out_of_domain_ranking_values(tmp_path, field_name, value):
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match=f"{field_name} must be between"):
        client.add("Invalid ranking record.", **{field_name: value})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"content": ""}, "content must be a non-empty string"),
        ({"content": "Valid.", "owner": ""}, "owner must be a non-empty string"),
        ({"content": "Valid.", "tags": "tvmaze"}, "tags must be a list"),
        ({"content": "Valid.", "visibility": "global"}, "visibility must be a list"),
        ({"content": "Valid.", "source": "manual"}, "source must be a mapping"),
        ({"content": "Valid.", "expires_at": "tomorrow"}, "expires_at must be"),
    ],
)
def test_sdk_rejects_malformed_canonical_fields(tmp_path, kwargs, message):
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match=message):
        client.add(**kwargs)


def test_expiry_is_canonicalized_and_historical_offsets_compare_as_instants(tmp_path):
    client = MemoryClient(home=tmp_path)
    now = datetime.now(timezone.utc)
    future_offset = (now + timedelta(minutes=30)).astimezone(
        timezone(timedelta(hours=-4))
    )
    past_offset = (now - timedelta(minutes=30)).astimezone(
        timezone(timedelta(hours=4))
    )
    canonical = client.add(
        "Canonical expiry sentinel.",
        expires_at=future_offset.isoformat(),
    )
    historical_future = client.add("Historical future offset sentinel.")
    historical_past = client.add("Historical past offset sentinel.")
    client.store.conn.execute(
        "UPDATE memories SET expires_at = ? WHERE id = ?",
        (future_offset.isoformat(), historical_future.id),
    )
    client.store.conn.execute(
        "UPDATE memories SET expires_at = ? WHERE id = ?",
        (past_offset.isoformat(), historical_past.id),
    )
    client.store.conn.commit()

    assert canonical.expires_at == future_offset.astimezone(timezone.utc).isoformat()
    assert historical_future.id in {
        hit.record.id for hit in client.search("historical future offset sentinel")
    }
    assert historical_past.id not in {
        hit.record.id for hit in client.search("historical past offset sentinel")
    }


def test_internal_profile_scope_and_snapshot_type_remain_valid(tmp_path):
    client = MemoryClient(home=tmp_path)
    profile = client.add("Imported profile memory.", scope="profile")
    snapshot_id = client.offload_context({"step": 1}, session_id="domain-test")

    assert profile.scope == "profile"
    assert client.get(snapshot_id).type == "snapshot"


def test_update_reuses_domain_validation_without_persisting_invalid_value(tmp_path):
    client = MemoryClient(home=tmp_path)
    memory = client.add("Valid record.", confidence=0.8)

    with pytest.raises(ValueError, match="confidence must be between"):
        client.update(memory.id, confidence=2.0)

    assert client.get(memory.id).confidence == 0.8
