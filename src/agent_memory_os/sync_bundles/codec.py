from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..timestamp_converters import convert_iso_to_stamp, stamp_to_dt
from .contract import BundleContract
from .registry import contract_for

_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "memory": frozenset(
        {
            "kind",
            "id",
            "owner",
            "scope",
            "type",
            "content",
            "summary",
            "tags",
            "visibility",
            "source",
            "confidence",
            "importance",
            "created_at",
            "updated_at",
            "decay_policy",
            "decay_half_life_days",
            "access_count",
            "pinned",
            "helpful_count",
            "unhelpful_count",
        }
    ),
    "link": frozenset(
        {
            "kind",
            "src_id",
            "dst_id",
            "relation",
            "weight",
            "created_at",
            "updated_at",
            "activation_count",
            "source",
        }
    ),
    "profile": frozenset(
        {"kind", "agent_id", "type_weights", "scope_weights", "updated_at"}
    ),
    "tombstone": frozenset({"kind", "id", "deleted_at"}),
    "team": frozenset({"kind", "id", "name", "updated_at", "members"}),
    "project": frozenset(
        {"kind", "id", "team_id", "name", "updated_at", "members"}
    ),
    "org_tombstone": frozenset({"kind", "tomb_kind", "id", "deleted_at"}),
}

_OPTIONAL_FIELDS: dict[str, frozenset[str]] = {
    "memory": frozenset({"acl_updated_at", "expires_at", "last_accessed_at"}),
    "link": frozenset({"last_activated_at"}),
    "profile": frozenset(),
    "tombstone": frozenset(),
    "team": frozenset(),
    "project": frozenset(),
    "org_tombstone": frozenset(),
}

_TIMESTAMP_FIELDS: dict[str, tuple[str, ...]] = {
    "memory": (
        "created_at",
        "updated_at",
        "acl_updated_at",
        "expires_at",
        "last_accessed_at",
    ),
    "link": ("created_at", "updated_at", "last_activated_at"),
    "profile": ("updated_at",),
    "tombstone": ("deleted_at",),
    "team": ("updated_at",),
    "project": ("updated_at",),
    "org_tombstone": ("deleted_at",),
}

_REQUIRED_TIMESTAMP_FIELDS: dict[str, frozenset[str]] = {
    kind: frozenset(fields) - _OPTIONAL_FIELDS[kind]
    for kind, fields in _TIMESTAMP_FIELDS.items()
}

_STRING_FIELDS = frozenset(
    {
        "id",
        "owner",
        "scope",
        "type",
        "content",
        "summary",
        "tags",
        "visibility",
        "source",
        "decay_policy",
        "src_id",
        "dst_id",
        "relation",
        "agent_id",
        "type_weights",
        "scope_weights",
        "name",
        "team_id",
        "tomb_kind",
    }
)
_NUMBER_FIELDS = frozenset({"confidence", "importance", "decay_half_life_days", "weight"})
_INTEGER_FIELDS = frozenset(
    {"access_count", "pinned", "helpful_count", "unhelpful_count", "activation_count"}
)


@dataclass(frozen=True)
class DecodedRecord:
    entry: dict[str, Any]
    converted_timestamp_fields: tuple[str, ...] = ()
    defaulted_fields: tuple[str, ...] = ()


def decode_header(value: object) -> tuple[BundleContract, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("bundle header must be a JSON object")
    if value.get("kind") != "bundle":
        raise ValueError("bundle header kind must be 'bundle'")

    contract = contract_for(value.get("version"))
    header = dict(value)
    if "node_name" in header and not isinstance(header["node_name"], str):
        raise ValueError("bundle header node_name must be a string")
    if contract.version == 4:
        unexpected = set(header) - {"kind", "version", "node_name"}
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"bundle v4 header has unsupported fields: {names}")
    return contract, header


def decode_record(
    contract: BundleContract,
    value: object,
) -> DecodedRecord | None:
    if not isinstance(value, dict):
        raise ValueError(f"bundle v{contract.version} record must be a JSON object")
    kind = value.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"bundle v{contract.version} record kind must be a string")
    if kind not in contract.record_kinds:
        if contract.allow_unknown_record_kinds:
            return None
        raise ValueError(f"bundle v{contract.version} record kind is unsupported: {kind}")

    entry = dict(value)
    required = set(_REQUIRED_FIELDS[kind])
    if kind == "memory" and contract.require_acl_clock:
        required.add("acl_updated_at")
    missing = sorted(field for field in required if field not in entry)
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"bundle v{contract.version} {kind} is missing fields: {names}")

    allowed = required | set(_OPTIONAL_FIELDS[kind])
    if contract.version == 4:
        unexpected = set(entry) - allowed
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(
                f"bundle v4 {kind} has unsupported fields: {names}"
            )

    _validate_primitive_fields(contract, kind, entry)

    defaulted: list[str] = []
    if kind == "memory" and not contract.require_acl_clock:
        if entry.get("acl_updated_at") is None:
            entry["acl_updated_at"] = entry.get("updated_at")
            defaulted.append("acl_updated_at")

    converted: list[str] = []
    for field in _TIMESTAMP_FIELDS[kind]:
        if field not in entry:
            continue
        timestamp = entry[field]
        if timestamp is None:
            if field in _REQUIRED_TIMESTAMP_FIELDS[kind] or (
                field == "acl_updated_at" and contract.require_acl_clock
            ):
                raise ValueError(
                    f"bundle v{contract.version} {kind}.{field} must be a timestamp"
                )
            continue
        if contract.timestamp_mode == "legacy-iso":
            try:
                stamp = convert_iso_to_stamp(timestamp)
            except ValueError as exc:
                raise ValueError(
                    f"bundle v{contract.version} {kind}.{field} must be a "
                    "supported legacy ISO timestamp"
                ) from exc
            if stamp != timestamp:
                converted.append(field)
            entry[field] = stamp
        else:
            try:
                stamp_to_dt(timestamp)
            except ValueError as exc:
                raise ValueError(
                    f"bundle v4 {kind}.{field} must be a canonical stamp"
                ) from exc

    return DecodedRecord(
        entry=entry,
        converted_timestamp_fields=tuple(converted),
        defaulted_fields=tuple(defaulted),
    )


def _validate_primitive_fields(
    contract: BundleContract,
    kind: str,
    entry: dict[str, Any],
) -> None:
    for field in _STRING_FIELDS & entry.keys():
        if not isinstance(entry[field], str):
            raise ValueError(
                f"bundle v{contract.version} {kind}.{field} must be a string"
            )
    for field in _NUMBER_FIELDS & entry.keys():
        value = entry[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"bundle v{contract.version} {kind}.{field} must be a number"
            )
    for field in _INTEGER_FIELDS & entry.keys():
        value = entry[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"bundle v{contract.version} {kind}.{field} must be an integer"
            )
    if "members" in entry and contract.version == 4:
        members = entry["members"]
        if not isinstance(members, list):
            raise ValueError(
                f"bundle v{contract.version} {kind}.members must be an array"
            )
        if any(
            not isinstance(member, str)
            for member in members
        ):
            raise ValueError(
                f"bundle v{contract.version} {kind}.members has invalid items"
            )
    if kind == "org_tombstone" and entry.get("tomb_kind") not in {"team", "project"}:
        raise ValueError(
            f"bundle v{contract.version} org_tombstone.tomb_kind is unsupported"
        )
