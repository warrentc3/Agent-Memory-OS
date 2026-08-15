from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from .codec import decode_header, decode_record
from .registry import CURRENT_BUNDLE_VERSION, contract_for


def convert_bundle(
    source: str | Path,
    target: str | Path,
) -> dict[str, object]:
    """Validate and convert a supported bundle into the current wire version.

    The target must not already exist. Output is installed atomically only
    after the complete source bundle has decoded and validated successfully.
    """
    source_path = Path(source).expanduser()
    target_path = Path(target).expanduser()
    if target_path.exists():
        raise FileExistsError(f"bundle conversion target already exists: {target_path}")
    if source_path.resolve() == target_path.resolve():
        raise ValueError("bundle conversion source and target must differ")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    current_contract = contract_for(CURRENT_BUNDLE_VERSION)
    record_counts: Counter[str] = Counter()
    converted_fields: Counter[str] = Counter()
    defaulted_fields: Counter[str] = Counter()
    ignored_records = 0
    project_seen = False

    temporary_path: Path | None = None
    try:
        with source_path.open("r", encoding="utf-8") as source_handle:
            source_contract, source_header = decode_header(
                json.loads(source_handle.readline())
            )
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                suffix=".jsonl",
                prefix=f".{target_path.name}.",
                dir=target_path.parent,
                delete=False,
            ) as target_handle:
                temporary_path = Path(target_handle.name)
                target_header = {
                    "kind": "bundle",
                    "version": CURRENT_BUNDLE_VERSION,
                }
                if source_header.get("node_name"):
                    target_header["node_name"] = source_header["node_name"]
                _, target_header = decode_header(target_header)
                target_handle.write(
                    json.dumps(target_header, ensure_ascii=False) + "\n"
                )

                for line_number, line in enumerate(source_handle, start=2):
                    try:
                        decoded = decode_record(
                            source_contract,
                            json.loads(line),
                        )
                        if decoded is not None:
                            kind = str(decoded.entry["kind"])
                            if kind == "team" and project_seen:
                                raise ValueError(
                                    "team records must precede project records"
                                )
                            if kind == "project":
                                project_seen = True
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise ValueError(
                            f"bundle conversion failed at line {line_number}: {exc}"
                        ) from exc
                    if decoded is None:
                        ignored_records += 1
                        continue

                    current = decode_record(current_contract, decoded.entry)
                    if current is None:
                        raise ValueError(
                            f"current bundle contract rejected line {line_number}"
                        )
                    target_handle.write(
                        json.dumps(current.entry, ensure_ascii=False) + "\n"
                    )
                    kind = str(current.entry["kind"])
                    record_counts[kind] += 1
                    for field in decoded.converted_timestamp_fields:
                        converted_fields[f"{kind}.{field}"] += 1
                    for field in decoded.defaulted_fields:
                        defaulted_fields[f"{kind}.{field}"] += 1

        if temporary_path is None:
            raise RuntimeError("bundle conversion produced no temporary artifact")
        os.link(temporary_path, target_path)
        temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "source_version": source_contract.version,
        "target_version": CURRENT_BUNDLE_VERSION,
        "records": dict(sorted(record_counts.items())),
        "converted_timestamp_fields": dict(sorted(converted_fields.items())),
        "defaulted_fields": dict(sorted(defaulted_fields.items())),
        "ignored_records": ignored_records,
    }
