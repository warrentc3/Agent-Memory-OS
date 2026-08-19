from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from agent_memory_os import timestamp_converters as converters


def test_stamp_to_dt_returns_aware_utc_datetime() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert converters.stamp_to_dt(
        "2026-08-11T09:15:42.123456Z"
    ) == datetime(2026, 8, 11, 9, 15, 42, 123456, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-11T09:15:42Z",
        "2026-08-11T09:15:42.123Z",
        "2026-08-11T09:15:42.1234567Z",
        "2026-08-11T09:15:42.123456+00:00",
    ],
)
def test_stamp_to_dt_rejects_noncanonical_text(value: str) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(
        ValueError,
        match=r"timestamp must match YYYY-MM-DDTHH:MM:SS\.ffffffZ",
    ):
        converters.stamp_to_dt(value)


def test_dt_to_stamp_converts_an_aware_datetime_to_utc() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    source = datetime(
        2026,
        8,
        11,
        14,
        45,
        42,
        123456,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )

    assert converters.dt_to_stamp(source) == "2026-08-11T09:15:42.123456Z"


@pytest.mark.parametrize(
    "value",
    [
        "9999-12-31T23:00:00-05:00",
        "0001-01-01T00:00:00+05:00",
    ],
)
def test_explicit_offset_conversion_reports_utc_range_overflow_as_value_error(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="datetime is outside Python's UTC range"):
        converters.convert_iso_offset(value)


def test_utc_now_dt_returns_an_aware_utc_datetime() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    now = converters.utc_now_dt()

    assert now.tzinfo is timezone.utc
    assert now.utcoffset() == timedelta(0)


def test_utc_now_stamp_emits_a_stamp() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"\.[0-9]{6}Z",
        converters.utc_now_stamp(),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-11T09:15:42Z", "2026-08-11T09:15:42.000000Z"),
        ("2026-08-11T14:45:42+05:30", "2026-08-11T09:15:42.000000Z"),
        ("2026-08-11T09:15:42.1", "2026-08-11T09:15:42.100000Z"),
        ("20260811T091542+00:00", "2026-08-11T09:15:42.000000Z"),
    ],
)
def test_convert_iso_to_stamp_converts_supported_shapes(
    value: str,
    expected: str,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert converters.convert_iso_to_stamp(value) == expected


def test_convert_iso_to_stamp_rejects_zero_date_sentinel() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(ValueError, match="zero-date sentinel"):
        converters.convert_iso_to_stamp("0000-00-00")


@pytest.mark.parametrize(
    "value",
    [
        "0000-00-00trailing",
        "0000:00:00Tnot-a-date",
    ],
)
def test_detector_rejects_zero_date_prefix_with_trailing_text(value: str) -> None:
    with pytest.raises(ValueError, match="cannot classify input datetime"):
        converters.detect_timestamp_shape(value)


@pytest.mark.parametrize(
    ("value", "expected_shape"),
    [
        ("20240928130000 -0400", "xmltv-offset"),
        ("20240928130000 0000", "xmltv-utc"),
        ("20240928130000 +0100", "xmltv-offset"),
    ],
)
def test_detector_identifies_full_length_xmltv_timestamps(
    value: str,
    expected_shape: str,
) -> None:
    assert converters.detect_timestamp_shape(value) == expected_shape


def test_convert_iso_to_stamp_rejects_detectable_non_iso_shape() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    value = "Mon 01 Jan 2024, 01:00PM"

    assert converters.detect_timestamp_shape(value) == "py-doc-12h"
    with pytest.raises(ValueError, match="unsupported ISO timestamp shape"):
        converters.convert_iso_to_stamp(value)


def test_now_distance_helpers_encode_from_and_to_direction(monkeypatch) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    fixed_now = datetime(2026, 8, 11, 9, 15, 42, tzinfo=timezone.utc)
    monkeypatch.setattr(
        converters,
        "utc_now_dt",
        lambda: fixed_now,
    )

    past = "2026-08-09T09:15:39.000000Z"
    future = "2026-08-13T09:15:45.000000Z"
    assert converters.stamp_distance_from_now_seconds(past) == 172_803.0
    assert converters.stamp_distance_to_now_seconds(past) == -172_803.0
    assert converters.stamp_distance_from_now_seconds(future) == -172_803.0
    assert converters.stamp_distance_to_now_seconds(future) == 172_803.0


def test_seconds_distance_from_and_to_now_produce_inverse_stamps(monkeypatch) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    fixed_now = datetime(2026, 8, 11, 9, 15, 42, tzinfo=timezone.utc)
    monkeypatch.setattr(converters, "utc_now_dt", lambda: fixed_now)

    assert (
        converters.seconds_distance_from_now_stamp(172_803.0)
        == "2026-08-09T09:15:39.000000Z"
    )
    assert (
        converters.seconds_distance_to_now_stamp(172_803.0)
        == "2026-08-13T09:15:45.000000Z"
    )


def test_explicit_dt_distance_helpers_encode_from_and_to_direction() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    base_dt = datetime(2026, 8, 11, 9, 15, 42, tzinfo=timezone.utc)
    stamp = "2026-08-09T09:15:39.000000Z"

    assert converters.stamp_distance_from_dt_seconds(stamp, base_dt) == 172_803.0
    assert converters.stamp_distance_to_dt_seconds(stamp, base_dt) == -172_803.0
    assert (
        converters.seconds_distance_from_dt_stamp(172_803.0, base_dt) == stamp
    )
    assert (
        converters.seconds_distance_to_dt_stamp(172_803.0, base_dt)
        == "2026-08-13T09:15:45.000000Z"
    )


def test_stamp_distance_to_stamp_seconds_encodes_to_direction() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    base_stamp = "2026-08-11T09:15:42.000000Z"

    assert (
        converters.stamp_distance_to_stamp_seconds(
            "2026-08-13T09:15:45.000000Z",
            base_stamp,
        )
        == 172_803.0
    )
    assert (
        converters.stamp_distance_to_stamp_seconds(
            "2026-08-09T09:15:39.000000Z",
            base_stamp,
        )
        == -172_803.0
    )


def test_days_distance_from_dt_stamp_preserves_fractional_days() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    base_dt = datetime(2026, 8, 11, 9, 15, 42, tzinfo=timezone.utc)

    assert (
        converters.days_distance_from_dt_stamp(1.5, base_dt)
        == "2026-08-09T21:15:42.000000Z"
    )


def test_stamp_distance_from_dt_days_preserves_fractional_days() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    base_dt = datetime(2026, 8, 11, 9, 15, 42, 500000, tzinfo=timezone.utc)

    assert (
        converters.stamp_distance_from_dt_days(
            "2026-08-09T21:15:42.000000Z",
            base_dt,
        )
        == pytest.approx(1.5 + (0.5 / 86_400))
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: converters.dt_to_stamp(datetime(2026, 8, 11)),
        lambda: converters.stamp_distance_from_dt_seconds(
            "2026-08-11T09:15:42.000000Z", datetime(2026, 8, 11)
        ),
        lambda: converters.stamp_distance_to_dt_seconds(
            "2026-08-11T09:15:42.000000Z", datetime(2026, 8, 11)
        ),
        lambda: converters.stamp_distance_from_dt_days(
            "2026-08-11T09:15:42.000000Z", datetime(2026, 8, 11)
        ),
        lambda: converters.days_distance_from_dt_stamp(
            1.0, datetime(2026, 8, 11)
        ),
        lambda: converters.seconds_distance_from_dt_stamp(
            1.0, datetime(2026, 8, 11)
        ),
        lambda: converters.seconds_distance_to_dt_stamp(
            1.0, datetime(2026, 8, 11)
        ),
    ],
)
def test_datetime_input_surfaces_reject_naive_values(
    call: Callable[[], object],
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(
        ValueError,
        match="datetime must include a timezone interpretation",
    ):
        call()


@pytest.mark.parametrize(
    ("converter", "value"),
    [
        (converters.convert_iso_z, "2024-1-2T3:4:5Z"),
        (
            converters.convert_iso_f_offset,
            "2024-01-02T03:04:05.1+0530",
        ),
        (
            converters.convert_space_offset,
            "2024-01-02 03:04:05Z",
        ),
        (converters.convert_exif_dateonly_utc, "2024:1:2"),
        (converters.convert_net_u_utc, "2024-1-2 3:4:5Z"),
    ],
)
def test_named_converter_rejects_text_outside_its_lexical_shape(
    converter,
    value: str,
) -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(ValueError, match="timestamp must match"):
        converter(value)


def test_arbitrary_fraction_is_truncated_to_six_digits() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.convert_iso_f_utc(
            "2026-08-08T12:34:56.12345678901234567890Z"
        )
        == "2026-08-08T12:34:56.123456Z"
    )


def test_fraction_truncation_never_carries_into_the_next_instant() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.convert_iso_f_utc("2026-08-08T23:59:59.9999999Z")
        == "2026-08-08T23:59:59.999999Z"
    )


def test_short_fraction_is_padded_to_six_digits() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.convert_iso_f_offset("2026-08-08T12:34:56.1+00:00")
        == "2026-08-08T12:34:56.100000Z"
    )


def test_detector_accepts_arbitrary_fraction_length() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.detect_timestamp_shape(
            "2026-08-08T12:34:56.12345678901234567890Z"
        )
        == "iso-f-utc"
    )


def test_fixed_three_digit_shape_remains_exact() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(ValueError, match="timestamp must match"):
        converters.convert_space_fff_utcword(
            "2026-08-08 12:34:56.1234 UTC"
        )


def test_amos_iso_offset_shapes_emit_canonical_zulu() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.convert_iso_offset("2030-01-01T00:00:00+05:30")
        == "2029-12-31T18:30:00.000000Z"
    )
    assert (
        converters.convert_iso_basic_utc("20990101T000000+00:00")
        == "2099-01-01T00:00:00.000000Z"
    )
    assert (
        converters.convert_iso_basic_offset("20990101T053000+05:30")
        == "2099-01-01T00:00:00.000000Z"
    )


def test_detector_prefers_exact_basic_utc_shape() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert (
        converters.detect_timestamp_shape("20990101T000000+00:00")
        == "iso-basic-utc"
    )
    assert (
        converters.detect_timestamp_shape("20990101T053000+05:30")
        == "iso-basic-offset"
    )


def test_exact_basic_utc_converter_rejects_nonzero_offset() -> None:
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    """
    with pytest.raises(ValueError, match="timestamp must match"):
        converters.convert_iso_basic_utc("20990101T053000+05:30")
