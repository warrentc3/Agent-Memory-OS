# AgentMemoryOS sync bundle contract

## Wire profile

A sync bundle is UTF-8 newline-delimited JSON. The first line is exactly one
bundle header. Every following line is one bundle record. Record order is
significant where references exist: memory records precede link records, and
team records precede project records.

The bundle version identifies this wire contract. It is independent of the
database schema version and the AgentMemoryOS package version.

The JSON Schema artifact for each version validates individual JSONL lines.
Whole-bundle invariants, ordering, timestamp interpretation, and conversion
are enforced by the corresponding Python codec.

## Support policy

AgentMemoryOS reads every version present in the bundle contract registry and
writes only `CURRENT_BUNDLE_VERSION`.

- **Supported for import** means a version-specific decoder validates the
  record and produces the current canonical internal record shape.
- **Supported for conversion** means the same decoder can feed the current
  encoder without unreported loss.
- **Supported for export** applies only to the current version.

Historical contracts are immutable. A new incompatible wire requirement
creates a new bundle version; it does not redefine an existing number.

## Version history

Versions 1 through 3 are reconstructed compatibility contracts. The original
implementation changed their accepted record shapes without maintaining
written schemas, so these profiles preserve behavior evidenced by the version
introducing commits and compatibility tests.

### Version 1

Record kinds: `memory`, `link`, and `profile`.

Timestamp fields accept the supported legacy ISO shapes. Decoding converts
them to canonical stamps. Unknown record kinds are ignored, matching the
historical importer.

### Version 2

Adds `tombstone`. It retains version 1 timestamp and unknown-kind behavior.

Memory records may omit `acl_updated_at`, which did not exist when this
version was introduced. The decoder defaults it to the decoded `updated_at`.

### Version 3

Adds `team`, `project`, and `org_tombstone`. It retains the legacy timestamp,
ACL-clock fallback, and unknown-kind behavior.

Historical version 3 accepted malformed organization `members` values and
coerced them during merge. The decoder preserves that compatibility; version
4 does not.

### Version 4

Version 4 is the timestamp-ubiquity contract.

- Every timestamp value is a canonical stamp:
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
- `acl_updated_at` is required on memory records.
- Optional timestamp fields are either absent, `null`, or canonical stamps.
- Unknown record kinds and unsupported fields are rejected.
- Organization `members` values are arrays of strings.

Version 4 decoding never converts timestamp representation. Invalid stamps
fail before merge logic runs.

## Conversion

`sync_bundles.converter.convert_bundle()` validates a supported source bundle,
decodes it to canonical records, validates those records against the current
contract, and atomically installs a new current-version bundle. It never
overwrites an existing target.

The conversion report identifies source and target versions, record counts,
converted timestamp fields, defaulted fields, and ignored legacy records. A
malformed source produces no target artifact.
