from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema.validators import validator_for
from referencing import Registry, Resource

import agent_memory_os.sync_bundles.converter as bundle_converter
from agent_memory_os import MemoryClient
from agent_memory_os.sync_bundles.codec import decode_header, decode_record
from agent_memory_os.sync_bundles.converter import convert_bundle
from agent_memory_os.sync_bundles.registry import (
    CURRENT_BUNDLE_VERSION,
    SUPPORTED_BUNDLE_VERSIONS,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "sync_bundles"


def _bundle_schema_validator(version: int):
    package = files("agent_memory_os.sync_bundles")
    registry = Registry()
    schemas: dict[int, dict[str, object]] = {}

    for supported_version in SUPPORTED_BUNDLE_VERSIONS:
        schema_path = Path(
            str(
                package
                / "schemas"
                / f"v{supported_version:03d}"
                / "bundle.schema.json"
            )
        ).resolve()
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$id"] = schema_path.as_uri()
        schemas[supported_version] = schema
        registry = registry.with_resource(
            schema_path.as_uri(),
            Resource.from_contents(schema),
        )

    schema = schemas[version]
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    return validator_type(schema, registry=registry)


def _legacy_memory() -> dict[str, object]:
    return {
        "kind": "memory",
        "id": "mem_legacy",
        "owner": "peer",
        "scope": "user",
        "type": "note",
        "content": "legacy bundle record",
        "summary": "",
        "tags": "[]",
        "visibility": '["global"]',
        "source": "{}",
        "confidence": 0.8,
        "importance": 0.5,
        "created_at": "2026-01-01T01:00:00+01:00",
        "updated_at": "2026-01-01T01:00:00+01:00",
        "expires_at": None,
        "decay_policy": "exponential",
        "decay_half_life_days": 30.0,
        "last_accessed_at": None,
        "access_count": 0,
        "pinned": 0,
        "helpful_count": 0,
        "unhelpful_count": 0,
    }


def test_bundle_contract_registry_defines_historical_record_kinds() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert CURRENT_BUNDLE_VERSION == 4
    assert SUPPORTED_BUNDLE_VERSIONS == frozenset({1, 2, 3, 4})

    v1, _ = decode_header({"kind": "bundle", "version": 1})
    v2, _ = decode_header({"kind": "bundle", "version": 2})
    v3, _ = decode_header({"kind": "bundle", "version": 3})
    v4, _ = decode_header({"kind": "bundle", "version": 4})

    assert v1.record_kinds == {"memory", "link", "profile"}
    assert v2.record_kinds == v1.record_kinds | {"tombstone"}
    assert v3.record_kinds == v2.record_kinds | {
        "team",
        "project",
        "org_tombstone",
    }
    assert v4.record_kinds == v3.record_kinds


def test_each_bundle_version_ships_a_machine_readable_schema() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    package = files("agent_memory_os.sync_bundles")

    for version in SUPPORTED_BUNDLE_VERSIONS:
        schema_path = (
            package
            / "schemas"
            / f"v{version:03d}"
            / "bundle.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        header = schema["$defs"]["header"]
        assert header["properties"]["version"]["const"] == version


@pytest.mark.parametrize(
    ("version", "allow_unknown"),
    [(1, True), (2, True), (3, True), (4, False)],
)
def test_bundle_schema_unknown_record_policy(
    version: int,
    allow_unknown: bool,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: regression for schema and decoder unknown-kind parity.
    """
    validator = _bundle_schema_validator(version)

    assert (
        validator.is_valid({"kind": "from_the_future", "value": 1}),
        validator.is_valid({"kind": ""}),
        validator.is_valid({"kind": 1}),
    ) == (allow_unknown, False, False)


@pytest.mark.parametrize(
    ("version", "known_kind"),
    [
        pytest.param(version, known_kind, id=f"v{version}-{known_kind}")
        for version in sorted(SUPPORTED_BUNDLE_VERSIONS)
        for known_kind in (
            "bundle",
            *sorted(
                decode_header({"kind": "bundle", "version": version})[
                    0
                ].record_kinds
            ),
        )
    ],
)
def test_bundle_schema_rejects_malformed_known_record(
    version: int,
    known_kind: str,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: covers every recognized kind in schema unknown-kind exclusions.
    """
    validator = _bundle_schema_validator(version)

    assert not validator.is_valid({"kind": known_kind})


@pytest.mark.parametrize(
    ("filename", "timestamp_field"),
    [
        ("v001-profile.jsonl", "updated_at"),
        ("v002-tombstone.jsonl", "deleted_at"),
        ("v003-team.jsonl", "updated_at"),
        ("v004-profile.jsonl", "updated_at"),
    ],
)
def test_golden_bundle_versions_decode_to_canonical_records(
    filename: str,
    timestamp_field: str,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    lines = [
        json.loads(line)
        for line in (_FIXTURES / filename).read_text(encoding="utf-8").splitlines()
    ]
    contract, _ = decode_header(lines[0])

    decoded = decode_record(contract, lines[1])

    assert decoded is not None
    assert decoded.entry[timestamp_field] == "2026-01-01T00:00:00.000000Z"


def test_invalid_v4_golden_bundle_rejects_offset_timestamp() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    lines = [
        json.loads(line)
        for line in (_FIXTURES / "v004-invalid-offset.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    contract, _ = decode_header(lines[0])

    with pytest.raises(ValueError, match="profile.updated_at must be a canonical stamp"):
        decode_record(contract, lines[1])


def test_v3_preserves_malformed_members_compatibility_but_v4_rejects_it() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    record = {
        "kind": "team",
        "id": "team",
        "name": "team",
        "updated_at": "2026-01-01T00:00:00.000000Z",
        "members": "not-an-array",
    }
    v3, _ = decode_header({"kind": "bundle", "version": 3})
    v4, _ = decode_header({"kind": "bundle", "version": 4})

    decoded = decode_record(v3, record)
    assert decoded is not None and decoded.entry["members"] == "not-an-array"
    with pytest.raises(ValueError, match="team.members must be an array"):
        decode_record(v4, record)


def test_legacy_decoder_converts_timestamps_and_defaults_acl_clock() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    contract, _ = decode_header({"kind": "bundle", "version": 2})

    decoded = decode_record(contract, _legacy_memory())

    assert decoded is not None
    assert decoded.entry["created_at"] == "2026-01-01T00:00:00.000000Z"
    assert decoded.entry["updated_at"] == "2026-01-01T00:00:00.000000Z"
    assert decoded.entry["acl_updated_at"] == "2026-01-01T00:00:00.000000Z"
    assert decoded.defaulted_fields == ("acl_updated_at",)


def test_v4_decoder_requires_stamps_and_acl_clock() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    contract, _ = decode_header({"kind": "bundle", "version": 4})
    legacy = _legacy_memory()

    with pytest.raises(ValueError, match="missing fields: acl_updated_at"):
        decode_record(contract, legacy)

    legacy["acl_updated_at"] = legacy["updated_at"]
    with pytest.raises(ValueError, match="memory.created_at must be a canonical stamp"):
        decode_record(contract, legacy)


def test_legacy_unknown_record_is_ignored_but_v4_rejects_it() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    v3, _ = decode_header({"kind": "bundle", "version": 3})
    v4, _ = decode_header({"kind": "bundle", "version": 4})
    unknown = {"kind": "from_the_future", "value": 1}

    assert decode_record(v3, unknown) is None
    with pytest.raises(ValueError, match="record kind is unsupported"):
        decode_record(v4, unknown)


def test_convert_legacy_bundle_writes_atomic_v4_and_report(tmp_path) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    source = tmp_path / "legacy.jsonl"
    target = tmp_path / "current.jsonl"
    source.write_text(
        json.dumps({"kind": "bundle", "version": 2, "node_name": "peer"})
        + "\n"
        + json.dumps(_legacy_memory())
        + "\n",
        encoding="utf-8",
    )

    report = convert_bundle(source, target)
    lines = [json.loads(line) for line in target.read_text().splitlines()]

    assert lines[0] == {"kind": "bundle", "version": 4, "node_name": "peer"}
    assert lines[1]["created_at"] == "2026-01-01T00:00:00.000000Z"
    assert lines[1]["acl_updated_at"] == "2026-01-01T00:00:00.000000Z"
    assert report == {
        "source_version": 2,
        "target_version": 4,
        "records": {"memory": 1},
        "converted_timestamp_fields": {
            "memory.acl_updated_at": 1,
            "memory.created_at": 1,
            "memory.updated_at": 1,
        },
        "defaulted_fields": {"memory.acl_updated_at": 1},
        "ignored_records": 0,
    }


def test_conversion_does_not_clobber_target_created_during_conversion(
    tmp_path,
    monkeypatch,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: regression for atomic no-clobber publication.
    """
    source = tmp_path / "source.jsonl"
    target = tmp_path / "current.jsonl"
    source.write_text(
        json.dumps({"kind": "bundle", "version": 4})
        + "\n"
        + json.dumps(
            {
                "kind": "profile",
                "agent_id": "peer",
                "type_weights": "{}",
                "scope_weights": "{}",
                "updated_at": "2026-01-01T00:00:00.000000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    original_decode_record = bundle_converter.decode_record
    target_created = False

    def create_target_then_decode(contract, value):
        nonlocal target_created
        if not target_created:
            target.write_text("created by another writer\n", encoding="utf-8")
            target_created = True
        return original_decode_record(contract, value)

    monkeypatch.setattr(bundle_converter, "decode_record", create_target_then_decode)

    with pytest.raises(FileExistsError):
        convert_bundle(source, target)

    assert target.read_text(encoding="utf-8") == "created by another writer\n"
    assert not list(tmp_path.glob(f".{target.name}.*.jsonl"))


def test_conversion_rejects_team_after_project(tmp_path) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: regression for v4 whole-bundle record ordering.
    """
    source = tmp_path / "out-of-order.jsonl"
    target = tmp_path / "current.jsonl"
    records = [
        {"kind": "bundle", "version": 4},
        {
            "kind": "project",
            "id": "project",
            "team_id": "team",
            "name": "Project",
            "updated_at": "2026-01-01T00:00:00.000000Z",
            "members": ["peer"],
        },
        {
            "kind": "team",
            "id": "team",
            "name": "Team",
            "updated_at": "2026-01-01T00:00:00.000000Z",
            "members": ["peer"],
        },
    ]
    source.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="team records must precede project records",
    ):
        convert_bundle(source, target)

    assert not target.exists()
    assert not list(tmp_path.glob(f".{target.name}.*.jsonl"))


def test_conversion_allows_project_without_team_record(tmp_path) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: preserves project-only incremental bundle conversion.
    """
    source = tmp_path / "project-only.jsonl"
    target = tmp_path / "current.jsonl"
    records = [
        {"kind": "bundle", "version": 4},
        {
            "kind": "project",
            "id": "project",
            "team_id": "team",
            "name": "Project",
            "updated_at": "2026-01-01T00:00:00.000000Z",
            "members": ["peer"],
        },
    ]
    source.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    report = convert_bundle(source, target)
    kinds = [
        json.loads(line)["kind"]
        for line in target.read_text(encoding="utf-8").splitlines()
    ]

    assert kinds == ["bundle", "project"]
    assert report["records"] == {"project": 1}


def test_failed_conversion_does_not_install_partial_target(tmp_path) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    source = tmp_path / "broken.jsonl"
    target = tmp_path / "current.jsonl"
    source.write_text(
        json.dumps({"kind": "bundle", "version": 2})
        + "\n"
        + json.dumps(_legacy_memory())
        + "\n"
        + "not-json\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 3"):
        convert_bundle(source, target)

    assert not target.exists()


def test_failed_v4_export_does_not_replace_existing_bundle(tmp_path) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    client = MemoryClient(home=tmp_path / "home")
    memory = client.add("Invalid export source.", visibility=["global"])
    client.store.conn.execute(
        "UPDATE memories SET updated_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+00:00", memory.id),
    )
    client.store.conn.commit()
    target = tmp_path / "existing.jsonl"
    target.write_text("existing bundle artifact\n", encoding="utf-8")

    with pytest.raises(ValueError, match="memory.updated_at must be a canonical stamp"):
        client.export_bundle(target)

    assert target.read_text(encoding="utf-8") == "existing bundle artifact\n"
    client.close()
