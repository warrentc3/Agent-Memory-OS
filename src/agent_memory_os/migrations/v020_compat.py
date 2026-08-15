"""Frozen compatibility surface for database migration v20.

Lineage:
- ``normalize_iso_timestamp`` entered live schema handling at commit bd659853.
- Migration v20 bound to that behavior at commit 1287c647.
- Commit d6884ee replaced the migration dependency with the stricter v22
  converter surface.
- The v22 stamp policy supersedes this helper for live writes; v20 retains the
  lenient ISO input and offset-output behavior required by legacy databases.
"""

from datetime import datetime, timezone


def normalize_iso_timestamp(value: str | None, *, field_name: str) -> str | None:
    """Preserve the ISO normalization contract consumed by migration v20."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
