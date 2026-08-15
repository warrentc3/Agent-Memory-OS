from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TimestampMode = Literal["legacy-iso", "stamp"]


@dataclass(frozen=True)
class BundleContract:
    """Immutable wire-contract properties for one sync bundle version."""

    version: int
    record_kinds: frozenset[str]
    timestamp_mode: TimestampMode
    allow_unknown_record_kinds: bool
    require_acl_clock: bool
