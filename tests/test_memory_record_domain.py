from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_memory_os.client import MemoryClient


@pytest.mark.parametrize("scope", ["", "workspace", "USER"])
def test_sdk_rejects_unknown_memory_scope(tmp_path, scope):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match="scope must be one of"):
        client.add("Invalid scope record.", scope=scope)


@pytest.mark.parametrize("memory_type", ["", "snapshot-ish", "FACT"])
def test_sdk_rejects_unknown_memory_type(tmp_path, memory_type):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
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
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
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
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError, match=message):
        client.add(**kwargs)


def test_expiry_requires_canonical_stamp(tmp_path):
    """Lineage:
    main: test_expiry_is_canonicalized_and_historical_offsets_compare_as_instants introduced bd659853@db-schema-v18.
    time-helper: renamed to test_expiry_requires_canonical_stamp d6884ee6@db-schema-v22.
    """
    client = MemoryClient(home=tmp_path)
    now = datetime.now(timezone.utc)
    future_stamp = (
        (now + timedelta(minutes=30))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    record = client.add(
        "Canonical expiry sentinel.",
        expires_at=future_stamp,
    )
    assert record.expires_at == future_stamp
    with pytest.raises(ValueError, match="expires_at must be a canonical stamp"):
        client.add(
            "Offset expiry sentinel.",
            expires_at="2099-01-01T00:00:00+00:00",
        )


def test_internal_profile_scope_and_snapshot_type_remain_valid(tmp_path):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    client = MemoryClient(home=tmp_path)
    profile = client.add("Imported profile memory.", scope="profile")
    snapshot_id = client.offload_context({"step": 1}, session_id="domain-test")

    assert profile.scope == "profile"
    assert client.get(snapshot_id).type == "snapshot"


def test_update_reuses_domain_validation_without_persisting_invalid_value(tmp_path):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    client = MemoryClient(home=tmp_path)
    memory = client.add("Valid record.", confidence=0.8)

    with pytest.raises(ValueError, match="confidence must be between"):
        client.update(memory.id, confidence=2.0)

    assert client.get(memory.id).confidence == 0.8


def test_legacy_nonstandard_domain_values_hydrate_without_poisoning_search(tmp_path):
    """Lineage:
    main: introduced dfc218f7@db-schema-v19.
    """
    client = MemoryClient(home=tmp_path)
    memory = client.add("Legacy application-defined record.")
    client.store.conn.execute(
        "UPDATE memories SET scope = ?, type = ? WHERE id = ?",
        ("session", "reflection", memory.id),
    )
    client.store.conn.commit()

    hydrated = client.get(memory.id)
    assert hydrated.scope == "session"
    assert hydrated.type == "reflection"
    assert memory.id in {
        hit.record.id for hit in client.search("legacy application defined record")
    }
