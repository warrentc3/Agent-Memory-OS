"""Convert known timestamp strings into canonical UTC Zulu stamps.

A ``stamp`` is AgentMemoryOS canonical timestamp text:

``YYYY-MM-DDTHH:MM:SS.ffffffZ``

Each lexical conversion function owns one fixed input shape. Shapes without
timezone context expose paired ``_local`` and ``_utc`` functions. Successful
conversions return stamps.

``utc_now_dt()`` returns a timezone-aware UTC ``datetime``.
``utc_now_stamp()`` returns the current instant as a stamp.
``dt_to_stamp()`` and ``stamp_to_dt()`` convert between those representations.
``convert_iso_to_stamp()`` accepts the supported ISO input shapes and interprets naive
input as UTC.

Signed distance names encode subtraction direction:

- ``<input>_distance_from_<base>_<output>`` means ``base - input``.
- ``<input>_distance_to_<base>_<output>`` means ``input - base``.

For seconds-to-stamp operations, ``from`` subtracts the supplied duration from
the base and ``to`` adds it to the base. Distance operations do not take an
absolute value or clamp negative results.

``_local`` functions use the host's per-date local timezone rules. Historical
offsets may therefore differ between operating-system timezone databases.

Fractional input beyond six digits is truncated, never rounded.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

__all__ = [
    "convert_compact_offset",
    "convert_compact_utc",
    "convert_exif_dateonly_local",
    "convert_exif_dateonly_utc",
    "convert_exif_f_naive_local",
    "convert_exif_f_naive_utc",
    "convert_exif_f_z",
    "convert_exif_fff_offset",
    "convert_exif_naive_local",
    "convert_exif_naive_utc",
    "convert_exif_offset",
    "convert_exif_z",
    "convert_iso_basic_offset",
    "convert_iso_basic_utc",
    "convert_iso_f_naive_local",
    "convert_iso_f_naive_utc",
    "convert_iso_f_offset",
    "convert_iso_f_utc",
    "convert_iso_offset",
    "convert_iso_to_stamp",
    "convert_iso_z",
    "convert_net_s_naive_local",
    "convert_net_s_naive_utc",
    "convert_net_u_utc",
    "convert_space_f_offset",
    "convert_space_fff_naive_local",
    "convert_space_fff_naive_utc",
    "convert_space_fff_utcword",
    "convert_space_naive_local",
    "convert_space_naive_utc",
    "convert_space_offset",
    "convert_space_utcword",
    "convert_unix_time_local",
    "convert_unix_time_utc",
    "convert_windows_filetime_local",
    "convert_windows_filetime_utc",
    "days_distance_from_dt_stamp",
    "detect_timestamp_shape",
    "dt_to_stamp",
    "seconds_distance_from_dt_stamp",
    "seconds_distance_from_now_stamp",
    "seconds_distance_to_dt_stamp",
    "seconds_distance_to_now_stamp",
    "stamp_distance_from_dt_days",
    "stamp_distance_from_dt_seconds",
    "stamp_distance_from_now_seconds",
    "stamp_distance_to_dt_seconds",
    "stamp_distance_to_now_seconds",
    "stamp_distance_to_stamp_seconds",
    "stamp_to_dt",
    "utc_now_dt",
    "utc_now_stamp",
]


_UTC = UTC
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=_UTC)
_WINDOWS_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=_UTC)

_ZERO_DATE = re.compile(r"0000[-:]00[-:]00")

_SHAPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "space-fff-utcword",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3} UTC"
        ),
    ),
    (
        "space-fff-naive",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3}"
        ),
    ),
    ("exif-dateonly", re.compile(r"[0-9]{4}:[0-9]{2}:[0-9]{2}")),
    (
        "exif-z",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    ),
    (
        "exif-naive",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "exif-offset",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "exif-fff-offset",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3}[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "compact-offset",
        re.compile(r"[0-9]{14} [-+][0-9]{4}"),
    ),
    ("compact-utc", re.compile(r"[0-9]{14} 0000")),
    (
        "py-doc-12h",
        re.compile(
            r"[A-Z][a-z]{2} [0-9]{2} [A-Z][a-z]{2} [0-9]{4}, "
            r"[0-9]{2}:[0-9]{2}[AP]M"
        ),
    ),
    (
        "iso-z",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    ),
    (
        "iso-offset",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "iso-f-offset",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "iso-f-utc",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+Z"
        ),
    ),
    (
        "iso-f-naive",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
    ),
    (
        "iso-basic-utc",
        re.compile(r"[0-9]{8}T[0-9]{6}\+00:00"),
    ),
    (
        "iso-basic-offset",
        re.compile(
            r"[0-9]{8}T[0-9]{6}[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "exif-f-z",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+Z"
        ),
    ),
    (
        "net-s-naive",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "net-u-utc",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    ),
    (
        "net-R-gmt",
        re.compile(
            r"[A-Z][a-z]{2}, [0-9]{2} [A-Z][a-z]{2} [0-9]{4} "
            r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT"
        ),
    ),
    (
        "net-g-enUS",
        re.compile(
            r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4} [0-9]{1,2}:[0-9]{2} [AP]M"
        ),
    ),
    (
        "net-F-enUS",
        re.compile(
            r"[A-Z][a-z]+, [A-Z][a-z]+ [0-9]{1,2}, [0-9]{4} "
            r"[0-9]{1,2}:[0-9]{2}:[0-9]{2} [AP]M"
        ),
    ),
    (
        "net-D-enUS",
        re.compile(r"[A-Z][a-z]+, [A-Z][a-z]+ [0-9]{1,2}, [0-9]{4}"),
    ),
    (
        "space-utcword",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC"
        ),
    ),
    (
        "space-naive",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "exif-f-naive",
        re.compile(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
    ),
    (
        "space-offset",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "space-f-offset",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+[-+][0-9]{2}:[0-9]{2}"
        ),
    ),
    (
        "distance-from-epoch",
        re.compile(r"[-+]?[0-9]+(?:\.[0-9]+)?"),
    ),
)


def detect_timestamp_shape(value: str) -> str | None:
    """Return the prior-art lexical shape ID for *value*.

    This function does not parse or normalize the timestamp and cannot choose a
    timezone policy for naive text. It returns ``None`` for the zero-date
    sentinel handled by the PowerShell prior art and raises ``ValueError`` when
    no known shape correlates.
    """
    value = _require_text(value)
    if _ZERO_DATE.fullmatch(value):
        return None
    for shape, pattern in _SHAPE_PATTERNS:
        if pattern.fullmatch(value):
            return shape
    raise ValueError(f"cannot classify input datetime: {value!r}")


def _require_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    return value


def _normalize_fraction(
    value: str,
    *,
    shape: str,
    minimum_digits: int,
    maximum_digits: int | None,
) -> str:
    if value.count(".") != 1:
        raise ValueError(f"timestamp must match {shape}")

    dot = value.index(".")
    end = dot + 1
    while end < len(value) and value[end] in "0123456789":
        end += 1

    digits = value[dot + 1 : end]
    if len(digits) < minimum_digits or (
        maximum_digits is not None and len(digits) > maximum_digits
    ):
        raise ValueError(f"timestamp must match {shape}")

    microseconds = digits[:6].ljust(6, "0")
    return f"{value[: dot + 1]}{microseconds}{value[end:]}"


def _parse(
    value: str,
    *,
    fmt: str,
    shape: str,
    lexical_pattern: str,
    fraction_digits: tuple[int, int | None] | None = None,
) -> datetime:
    value = _require_text(value)
    if re.fullmatch(lexical_pattern, value) is None:
        raise ValueError(f"timestamp must match {shape}")
    if fraction_digits is not None:
        value = _normalize_fraction(
            value,
            shape=shape,
            minimum_digits=fraction_digits[0],
            maximum_digits=fraction_digits[1],
        )
    try:
        return datetime.strptime(  # noqa: DTZ007 - callers apply timezone policy.
            value, fmt
        )
    except ValueError as exc:
        raise ValueError(f"timestamp must match {shape}") from exc

def _require_aware_dt(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone interpretation")
    return value


def dt_to_stamp(value: datetime) -> str:
    value = _require_aware_dt(value)
    return (
        value.astimezone(_UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )

def stamp_to_dt(value: str) -> datetime:
    """Parse canonical UTC text into a timezone-aware UTC datetime."""
    parsed = _parse(
        value,
        fmt="%Y-%m-%dT%H:%M:%S.%fZ",
        shape="YYYY-MM-DDTHH:MM:SS.ffffffZ",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}" r"\.[0-9]{6}Z"
        ),
    )
    return parsed.replace(tzinfo=_UTC)

def utc_now_dt() -> datetime:
    """Return the current instant as timezone-aware UTC datetime."""
    return datetime.now(_UTC)


def utc_now_stamp() -> str:
    """Return the current instant as canonical UTC microsecond Zulu text."""
    return dt_to_stamp(datetime.now(_UTC))


# ---------------------------------------------------------------------------
# Signed timestamp distances
#
# "from BASE" => BASE - input
# "to BASE"   => input - BASE
# ---------------------------------------------------------------------------


def stamp_distance_from_now_seconds(stamp: str) -> float:
    """Return ``now - stamp`` in seconds; past stamps are positive."""
    return (utc_now_dt() - stamp_to_dt(stamp)).total_seconds()


def stamp_distance_to_now_seconds(stamp: str) -> float:
    """Return ``stamp - now`` in seconds; future stamps are positive."""
    return (stamp_to_dt(stamp) - utc_now_dt()).total_seconds()


def seconds_distance_from_now_stamp(seconds: float) -> str:
    """Return the stamp ``seconds`` before now; positive values move backward."""
    return dt_to_stamp(utc_now_dt() - timedelta(seconds=seconds))


def seconds_distance_to_now_stamp(seconds: float) -> str:
    """Return the stamp ``seconds`` after now; positive values move forward."""
    return dt_to_stamp(utc_now_dt() + timedelta(seconds=seconds))


def stamp_distance_from_dt_seconds(stamp: str, base_dt: datetime) -> float:
    """Return ``base_dt - stamp`` in seconds."""
    base_dt = _require_aware_dt(base_dt)
    return (base_dt - stamp_to_dt(stamp)).total_seconds()


def stamp_distance_to_dt_seconds(stamp: str, base_dt: datetime) -> float:
    """Return ``stamp - base_dt`` in seconds."""
    base_dt = _require_aware_dt(base_dt)
    return (stamp_to_dt(stamp) - base_dt).total_seconds()


def stamp_distance_to_stamp_seconds(stamp: str, base_stamp: str) -> float:
    """Return ``stamp - base_stamp`` in seconds."""
    return (stamp_to_dt(stamp) - stamp_to_dt(base_stamp)).total_seconds()


def stamp_distance_from_dt_days(stamp: str, base_dt: datetime) -> float:
    """Return ``base_dt - stamp`` in days."""
    base_dt = _require_aware_dt(base_dt)
    return (base_dt - stamp_to_dt(stamp)) / timedelta(days=1)


def days_distance_from_dt_stamp(days: float, base_dt: datetime) -> str:
    """Return the stamp ``days`` before ``base_dt``."""
    base_dt = _require_aware_dt(base_dt)
    return dt_to_stamp(base_dt - timedelta(days=days))


def seconds_distance_from_dt_stamp(seconds: float, base_dt: datetime) -> str:
    """Return the stamp ``seconds`` before ``base_dt``."""
    base_dt = _require_aware_dt(base_dt)
    return dt_to_stamp(base_dt - timedelta(seconds=seconds))


def seconds_distance_to_dt_stamp(seconds: float, base_dt: datetime) -> str:
    """Return the stamp ``seconds`` after ``base_dt``."""
    base_dt = _require_aware_dt(base_dt)
    return dt_to_stamp(base_dt + timedelta(seconds=seconds))


def _local_wall_to_utc(value: datetime) -> datetime:
    if value.tzinfo is not None or value.utcoffset() is not None:
        raise ValueError("local wall time must be naive")

    if sys.platform != "win32":
        try:
            return value.astimezone(_UTC)
        except (OSError, OverflowError, ValueError) as exc:
            raise ValueError("local time is outside the host timezone range") from exc

    # Windows' C runtime cannot resolve some otherwise-valid datetime values,
    # including local midnight at the Unix epoch and pre-1970 FILETIME values.
    # The native dynamic-time-zone API covers the full SYSTEMTIME range and
    # applies the host's per-date UTC offset.
    import ctypes
    from ctypes import wintypes

    class _SystemTime(ctypes.Structure):
        _fields_ = [
            ("year", wintypes.WORD),
            ("month", wintypes.WORD),
            ("day_of_week", wintypes.WORD),
            ("day", wintypes.WORD),
            ("hour", wintypes.WORD),
            ("minute", wintypes.WORD),
            ("second", wintypes.WORD),
            ("milliseconds", wintypes.WORD),
        ]

    source = _SystemTime(
        value.year,
        value.month,
        0,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond // 1_000,
    )
    target = _SystemTime()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = kernel32.TzSpecificLocalTimeToSystemTimeEx
    convert.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_SystemTime),
        ctypes.POINTER(_SystemTime),
    )
    convert.restype = wintypes.BOOL

    ctypes.set_last_error(0)
    if not convert(None, ctypes.byref(source), ctypes.byref(target)):
        error = ctypes.get_last_error()
        raise ValueError(
            f"local time cannot be resolved in the host timezone (Windows error {error})"
        )

    try:
        return datetime(
            target.year,
            target.month,
            target.day,
            target.hour,
            target.minute,
            target.second,
            value.microsecond,
            tzinfo=_UTC,
        )
    except ValueError as exc:
        raise ValueError("local time is outside Python's datetime range") from exc


def _from_explicit_offset(
    value: str,
    *,
    fmt: str,
    shape: str,
    lexical_pattern: str,
    fraction_digits: tuple[int, int | None] | None = None,
) -> str:
    return dt_to_stamp(
        _parse(
            value,
            fmt=fmt,
            shape=shape,
            lexical_pattern=lexical_pattern,
            fraction_digits=fraction_digits,
        )
    )


def _from_explicit_utc(
    value: str,
    *,
    fmt: str,
    shape: str,
    lexical_pattern: str,
    fraction_digits: tuple[int, int | None] | None = None,
) -> str:
    parsed = _parse(
        value,
        fmt=fmt,
        shape=shape,
        lexical_pattern=lexical_pattern,
        fraction_digits=fraction_digits,
    )
    return dt_to_stamp(parsed.replace(tzinfo=_UTC))


def _from_naive_local(
    value: str,
    *,
    fmt: str,
    shape: str,
    lexical_pattern: str,
    fraction_digits: tuple[int, int | None] | None = None,
) -> str:
    parsed = _parse(
        value,
        fmt=fmt,
        shape=shape,
        lexical_pattern=lexical_pattern,
        fraction_digits=fraction_digits,
    )
    return dt_to_stamp(_local_wall_to_utc(parsed))


def _from_naive_utc(
    value: str,
    *,
    fmt: str,
    shape: str,
    lexical_pattern: str,
    fraction_digits: tuple[int, int | None] | None = None,
) -> str:
    parsed = _parse(
        value,
        fmt=fmt,
        shape=shape,
        lexical_pattern=lexical_pattern,
        fraction_digits=fraction_digits,
    )
    return dt_to_stamp(parsed.replace(tzinfo=_UTC))


# Detector class: space-fff-utcword
def convert_space_fff_utcword(value: str) -> str:
    """Detector class: ``space-fff-utcword``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y-%m-%d %H:%M:%S.%f UTC",
        shape="YYYY-MM-DD HH:MM:SS.fff UTC",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3} UTC"
        ),
        fraction_digits=(3, 3),
    )


# Detector class: space-fff-naive
def convert_space_fff_naive_local(value: str) -> str:
    """Detector class: ``space-fff-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y-%m-%d %H:%M:%S.%f",
        shape="YYYY-MM-DD HH:MM:SS.fff",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3}"
        ),
        fraction_digits=(3, 3),
    )


def convert_space_fff_naive_utc(value: str) -> str:
    """Detector class: ``space-fff-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y-%m-%d %H:%M:%S.%f",
        shape="YYYY-MM-DD HH:MM:SS.fff",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3}"
        ),
        fraction_digits=(3, 3),
    )


# Detector class: exif-dateonly
def convert_exif_dateonly_local(value: str) -> str:
    """Detector class: ``exif-dateonly``. Assume local midnight and convert."""
    return _from_naive_local(
        value,
        fmt="%Y:%m:%d",
        shape="YYYY:MM:DD",
        lexical_pattern=r"[0-9]{4}:[0-9]{2}:[0-9]{2}",
    )


def convert_exif_dateonly_utc(value: str) -> str:
    """Detector class: ``exif-dateonly``. Assume UTC midnight and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y:%m:%d",
        shape="YYYY:MM:DD",
        lexical_pattern=r"[0-9]{4}:[0-9]{2}:[0-9]{2}",
    )


# Detector class: exif-z
def convert_exif_z(value: str) -> str:
    """Detector class: ``exif-z``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y:%m:%d %H:%M:%SZ",
        shape="YYYY:MM:DD HH:MM:SSZ",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    )


# Detector class: exif-naive
def convert_exif_naive_local(value: str) -> str:
    """Detector class: ``exif-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y:%m:%d %H:%M:%S",
        shape="YYYY:MM:DD HH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


def convert_exif_naive_utc(value: str) -> str:
    """Detector class: ``exif-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y:%m:%d %H:%M:%S",
        shape="YYYY:MM:DD HH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: exif-offset
def convert_exif_offset(value: str) -> str:
    """Detector class: ``exif-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y:%m:%d %H:%M:%S%z",
        shape="YYYY:MM:DD HH:MM:SS+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: exif-fff-offset
def convert_exif_fff_offset(value: str) -> str:
    """Detector class: ``exif-fff-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y:%m:%d %H:%M:%S.%f%z",
        shape="YYYY:MM:DD HH:MM:SS.fff+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]{3}[-+][0-9]{2}:[0-9]{2}"
        ),
        fraction_digits=(3, 3),
    )


# Detector class: compact-offset
def convert_compact_offset(value: str) -> str:
    """Detector class: ``compact-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y%m%d%H%M%S %z",
        shape="YYYYMMDDHHMMSS +HHMM",
        lexical_pattern=r"[0-9]{14} [-+][0-9]{4}",
    )


# Detector class: compact-utc
def convert_compact_utc(value: str) -> str:
    """Detector class: ``compact-utc``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y%m%d%H%M%S 0000",
        shape="YYYYMMDDHHMMSS 0000",
        lexical_pattern=r"[0-9]{14} 0000",
    )


# Detector class: iso-z
def convert_iso_z(value: str) -> str:
    """Detector class: ``iso-z``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y-%m-%dT%H:%M:%SZ",
        shape="YYYY-MM-DDTHH:MM:SSZ",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    )


# Detector class: iso-offset
def convert_iso_offset(value: str) -> str:
    """Detector class: ``iso-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y-%m-%dT%H:%M:%S%z",
        shape="YYYY-MM-DDTHH:MM:SS+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: iso-f-offset
def convert_iso_f_offset(value: str) -> str:
    """Detector class: ``iso-f-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y-%m-%dT%H:%M:%S.%f%z",
        shape="YYYY-MM-DDTHH:MM:SS.<fraction>+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+[-+][0-9]{2}:[0-9]{2}"
        ),
        fraction_digits=(1, None),
    )


# Detector class: iso-f-utc
def convert_iso_f_utc(value: str) -> str:
    """Detector class: ``iso-f-utc``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y-%m-%dT%H:%M:%S.%fZ",
        shape="YYYY-MM-DDTHH:MM:SS.<fraction>Z",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+Z"
        ),
        fraction_digits=(1, None),
    )


# Detector class: iso-f-naive
def convert_iso_f_naive_local(value: str) -> str:
    """Detector class: ``iso-f-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y-%m-%dT%H:%M:%S.%f",
        shape="YYYY-MM-DDTHH:MM:SS.<fraction>",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
        fraction_digits=(1, None),
    )


def convert_iso_f_naive_utc(value: str) -> str:
    """Detector class: ``iso-f-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y-%m-%dT%H:%M:%S.%f",
        shape="YYYY-MM-DDTHH:MM:SS.<fraction>",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
        fraction_digits=(1, None),
    )


# Detector class: iso-basic-utc
def convert_iso_basic_utc(value: str) -> str:
    """Detector class: ``iso-basic-utc``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y%m%dT%H%M%S+00:00",
        shape="YYYYMMDDTHHMMSS+00:00",
        lexical_pattern=r"[0-9]{8}T[0-9]{6}\+00:00",
    )


# Detector class: iso-basic-offset
def convert_iso_basic_offset(value: str) -> str:
    """Detector class: ``iso-basic-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y%m%dT%H%M%S%z",
        shape="YYYYMMDDTHHMMSS+HH:MM",
        lexical_pattern=r"[0-9]{8}T[0-9]{6}[-+][0-9]{2}:[0-9]{2}",
    )


# Detector class: exif-f-z
def convert_exif_f_z(value: str) -> str:
    """Detector class: ``exif-f-z``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y:%m:%d %H:%M:%S.%fZ",
        shape="YYYY:MM:DD HH:MM:SS.<fraction>Z",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+Z"
        ),
        fraction_digits=(1, None),
    )


# Detector class: net-s-naive
def convert_net_s_naive_local(value: str) -> str:
    """Detector class: ``net-s-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y-%m-%dT%H:%M:%S",
        shape="YYYY-MM-DDTHH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


def convert_net_s_naive_utc(value: str) -> str:
    """Detector class: ``net-s-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y-%m-%dT%H:%M:%S",
        shape="YYYY-MM-DDTHH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: net-u-utc
def convert_net_u_utc(value: str) -> str:
    """Detector class: ``net-u-utc``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y-%m-%d %H:%M:%SZ",
        shape="YYYY-MM-DD HH:MM:SSZ",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}Z"
        ),
    )


# Detector class: space-utcword
def convert_space_utcword(value: str) -> str:
    """Detector class: ``space-utcword``. Convert its timestamp shape."""
    return _from_explicit_utc(
        value,
        fmt="%Y-%m-%d %H:%M:%S UTC",
        shape="YYYY-MM-DD HH:MM:SS UTC",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC"
        ),
    )


# Detector class: space-naive
def convert_space_naive_local(value: str) -> str:
    """Detector class: ``space-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y-%m-%d %H:%M:%S",
        shape="YYYY-MM-DD HH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


def convert_space_naive_utc(value: str) -> str:
    """Detector class: ``space-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y-%m-%d %H:%M:%S",
        shape="YYYY-MM-DD HH:MM:SS",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: exif-f-naive
def convert_exif_f_naive_local(value: str) -> str:
    """Detector class: ``exif-f-naive``. Assume local time and convert."""
    return _from_naive_local(
        value,
        fmt="%Y:%m:%d %H:%M:%S.%f",
        shape="YYYY:MM:DD HH:MM:SS.<fraction>",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
        fraction_digits=(1, None),
    )


def convert_exif_f_naive_utc(value: str) -> str:
    """Detector class: ``exif-f-naive``. Assume UTC and convert."""
    return _from_naive_utc(
        value,
        fmt="%Y:%m:%d %H:%M:%S.%f",
        shape="YYYY:MM:DD HH:MM:SS.<fraction>",
        lexical_pattern=(
            r"[0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+"
        ),
        fraction_digits=(1, None),
    )


# Detector class: space-offset
def convert_space_offset(value: str) -> str:
    """Detector class: ``space-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y-%m-%d %H:%M:%S%z",
        shape="YYYY-MM-DD HH:MM:SS+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"[-+][0-9]{2}:[0-9]{2}"
        ),
    )


# Detector class: space-f-offset
def convert_space_f_offset(value: str) -> str:
    """Detector class: ``space-f-offset``. Convert its timestamp shape."""
    return _from_explicit_offset(
        value,
        fmt="%Y-%m-%d %H:%M:%S.%f%z",
        shape="YYYY-MM-DD HH:MM:SS.<fraction>+HH:MM",
        lexical_pattern=(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"\.[0-9]+[-+][0-9]{2}:[0-9]{2}"
        ),
        fraction_digits=(1, None),
    )


# Detector class: distance-from-epoch
def _parse_unix_time(value: str) -> datetime:
    value = _require_text(value)
    if not re.fullmatch(r"[-+]?[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError("Unix time must be decimal seconds")
    try:
        seconds = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Unix time must be decimal seconds") from exc

    # int() truncates toward zero after conversion to integral microseconds.
    microseconds = int(seconds * 1_000_000)
    try:
        return _UNIX_EPOCH + timedelta(microseconds=microseconds)
    except OverflowError as exc:
        raise ValueError("Unix time is outside Python's datetime range") from exc


def convert_unix_time_local(value: str) -> str:
    """Detector class: ``distance-from-epoch``.

    Convert an offset-adjusted Unix-like value by treating its decoded wall
    fields as local time. Use ``convert_unix_time_utc`` for standard Unix time.
    """
    parsed = _parse_unix_time(value).replace(tzinfo=None)
    return dt_to_stamp(_local_wall_to_utc(parsed))


def convert_unix_time_utc(value: str) -> str:
    """Detector class: ``distance-from-epoch``. Convert standard Unix time."""
    return dt_to_stamp(_parse_unix_time(value))


def _parse_windows_filetime(value: str) -> datetime:
    value = _require_text(value)
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Windows FILETIME must be an unsigned decimal integer")

    intervals_100ns = int(value)
    if intervals_100ns > (1 << 64) - 1:
        raise ValueError("Windows FILETIME must fit in an unsigned 64-bit integer")

    # Ten 100-nanosecond intervals make one microsecond; discard the remainder.
    microseconds = intervals_100ns // 10
    try:
        return _WINDOWS_FILETIME_EPOCH + timedelta(microseconds=microseconds)
    except OverflowError as exc:
        raise ValueError("Windows FILETIME is outside Python's datetime range") from exc


def convert_windows_filetime_local(value: str) -> str:
    """Detector class: ``distance-from-epoch``.

    Convert an offset-adjusted FILETIME-like value by treating its decoded wall
    fields as local time. Use ``convert_windows_filetime_utc`` for standard
    Windows FILETIME.
    """
    parsed = _parse_windows_filetime(value).replace(tzinfo=None)
    return dt_to_stamp(_local_wall_to_utc(parsed))


def convert_windows_filetime_utc(value: str) -> str:
    """Detector class: ``distance-from-epoch``. Convert standard FILETIME."""
    return dt_to_stamp(_parse_windows_filetime(value))


_ISO_TO_STAMP = {
    "iso-z": convert_iso_z,
    "iso-offset": convert_iso_offset,
    "iso-f-offset": convert_iso_f_offset,
    "iso-f-utc": convert_iso_f_utc,
    "iso-f-naive": convert_iso_f_naive_utc,
    "iso-basic-utc": convert_iso_basic_utc,
    "iso-basic-offset": convert_iso_basic_offset,
    "net-s-naive": convert_net_s_naive_utc,
}


def convert_iso_to_stamp(value: str) -> str:
    """Convert an accepted ISO shape to a stamp; interpret naive input as UTC. LEGACY & MIGRATION USE ONLY."""
    shape = detect_timestamp_shape(value)
    if shape is None:
        raise ValueError("zero-date sentinel is not a timestamp")

    converter = _ISO_TO_STAMP.get(shape)
    if converter is None:
        raise ValueError(f"unsupported ISO timestamp shape: {shape}")

    return converter(value)


def normalize_iso_timestamp(value: str | None, *, field_name: str) -> str | None:
    """Canonicalize an accepted ISO timestamp using explicit shape converters. LEGACY & MIGRATION USE ONLY."""
    if value is None:
        return None
    try:
        return convert_iso_to_stamp(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
