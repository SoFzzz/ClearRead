"""Conversion between plain JSON-like Python values and Firestore typed values."""

import math
import re
from datetime import UTC, datetime
from typing import Any

_TIMESTAMP = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$"
)


def encode_value(value: Any) -> dict[str, Any]:
    # bool is a subclass of int, so it must be tested first.
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers cannot be stored")
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, datetime):
        return {"timestampValue": _format_timestamp(value)}
    if isinstance(value, list | tuple):
        return {"arrayValue": {"values": [encode_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": encode_fields(value)}}
    raise TypeError(f"unsupported value type: {type(value).__name__}")


def encode_fields(mapping: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(key, str) for key in mapping):
        raise TypeError("map keys must be strings")
    return {key: encode_value(value) for key, value in mapping.items()}


def decode_value(raw: dict[str, Any]) -> Any:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ValueError("a typed value has exactly one member")
    ((kind, payload),) = raw.items()
    if kind == "nullValue":
        return None
    if kind in ("booleanValue", "stringValue"):
        return payload
    if kind == "integerValue":
        return int(payload)
    if kind == "doubleValue":
        return float(payload)
    if kind == "timestampValue":
        return _parse_timestamp(payload)
    if kind == "arrayValue":
        return [decode_value(item) for item in payload.get("values", [])]
    if kind == "mapValue":
        return decode_fields(payload.get("fields", {}))
    raise ValueError(f"unsupported value kind: {kind}")


def decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: decode_value(raw) for key, raw in fields.items()}


def _format_timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(text: str) -> datetime:
    match = _TIMESTAMP.match(text)
    if match is None:
        raise ValueError("invalid timestamp")
    stem, fraction, zone = match.groups()
    # Firestore may return nanoseconds; datetime keeps microseconds.
    micros = (fraction or "0")[:6].ljust(6, "0")
    offset = "+00:00" if zone == "Z" else zone
    return datetime.fromisoformat(f"{stem}.{micros}{offset}").astimezone(UTC)
