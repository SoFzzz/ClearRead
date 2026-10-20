"""The Firestore typed-value codec (profile storage)."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from clearread_backend.firestore_values import (
    decode_fields,
    decode_value,
    encode_fields,
    encode_value,
)


@pytest.mark.parametrize(
    "value, encoded",
    [
        (None, {"nullValue": None}),
        (True, {"booleanValue": True}),
        (False, {"booleanValue": False}),
        (0, {"integerValue": "0"}),
        (-7, {"integerValue": "-7"}),
        (2**40, {"integerValue": "1099511627776"}),
        (1.5, {"doubleValue": 1.5}),
        (1.0, {"doubleValue": 1.0}),
        ("", {"stringValue": ""}),
        ("niño", {"stringValue": "niño"}),
        ([], {"arrayValue": {"values": []}}),
        ({}, {"mapValue": {"fields": {}}}),
    ],
)
def test_scalars_and_empty_containers_encode_to_one_typed_member(
    value: Any, encoded: dict
) -> None:
    assert encode_value(value) == encoded
    assert decode_value(encoded) == value


def test_booleans_are_not_encoded_as_integers() -> None:
    assert "booleanValue" in encode_value(True)
    assert "integerValue" not in encode_value(True)
    assert decode_value(encode_value(1)) == 1
    assert decode_value(encode_value(1)) is not True


def test_ints_and_floats_keep_their_type_through_a_round_trip() -> None:
    decoded = decode_value(encode_value([1, 1.0, True]))
    assert [type(item) for item in decoded] == [int, float, bool]


def test_nested_maps_and_arrays_round_trip() -> None:
    value = {
        "font": {"family": "Lexend", "size": 18, "scale": 1.25},
        "flags": [True, False, None],
        "rows": [{"word": "casa", "tags": ["a", "b"]}, {"word": "luz", "tags": []}],
    }
    assert decode_fields(encode_fields(value)) == value


def test_timestamps_are_sent_in_utc_with_z() -> None:
    moment = datetime(2026, 10, 19, 12, 30, 5, tzinfo=timezone(timedelta(hours=-3)))
    assert encode_value(moment) == {"timestampValue": "2026-10-19T15:30:05Z"}


def test_timestamps_round_trip_with_microseconds() -> None:
    moment = datetime(2026, 10, 19, 15, 30, 5, 123456, tzinfo=UTC)
    assert decode_value(encode_value(moment)) == moment


@pytest.mark.parametrize(
    "text, expected_micro",
    [
        ("2026-10-19T15:30:05Z", 0),
        ("2026-10-19T15:30:05.5Z", 500000),
        ("2026-10-19T15:30:05.123456789Z", 123456),
    ],
)
def test_firestore_timestamps_with_any_fraction_are_read(
    text: str, expected_micro: int
) -> None:
    decoded = decode_value({"timestampValue": text})
    assert decoded.microsecond == expected_micro
    assert decoded.tzinfo is not None


def test_a_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_value(datetime(2026, 10, 19))


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        encode_value(value)


@pytest.mark.parametrize("value", [b"bytes", {1: "numeric key"}, {"a": object()}])
def test_unsupported_values_are_rejected(value: Any) -> None:
    with pytest.raises(TypeError):
        encode_value(value)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"stringValue": "a", "integerValue": "1"},
        {"geoPointValue": {"latitude": 1}},
        {"timestampValue": "yesterday"},
        {"integerValue": "many"},
        "not a dict",
    ],
)
def test_malformed_or_unknown_typed_values_are_rejected(raw: Any) -> None:
    with pytest.raises(ValueError):
        decode_value(raw)


def test_arrays_and_maps_without_members_decode_as_empty() -> None:
    assert decode_value({"arrayValue": {}}) == []
    assert decode_value({"mapValue": {}}) == {}
