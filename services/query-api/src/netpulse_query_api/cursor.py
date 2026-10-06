"""Encoding and decoding for versioned daily reliability cursors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import date
from typing import Any

from pydantic import ValidationError

from netpulse_query_api.models import CursorKey, DailyReliabilityFilters, SourceKind

_MAX_CURSOR_LENGTH = 2048
_KEY_FIELDS = ("date_utc", "agent_id", "endpoint_id", "source_kind", "probe_type")
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_URLSAFE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]*\Z")
_V2_HEADER = b"NPC\x02"
_SOURCE_KINDS = (SourceKind.NETWORK_MEASUREMENT, SourceKind.SERVICE_CHECK)


class CursorError(ValueError):
    """Raised when a pagination cursor cannot be used."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _filter_fingerprint(filters: DailyReliabilityFilters) -> str:
    return hashlib.sha256(_canonical_json(filters.fingerprint_payload())).hexdigest()


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _encode_identifier(value: str) -> bytes:
    if not 1 <= len(value) <= 128:
        raise ValueError
    scalars = [ord(character) for character in value]
    if any(0xD800 <= scalar <= 0xDFFF for scalar in scalars):
        raise ValueError
    return bytes([len(value)]) + b"".join(scalar.to_bytes(3, "big") for scalar in scalars)


def encode_cursor(key: CursorKey, filters: DailyReliabilityFilters) -> str:
    """Encode v2 without compression: at most 1,195 bytes / 1,594 characters.

    Layout: magic/version (4), date ordinal (3), source (1), three scalar-count
    prefixes (1 each) and 3-byte big-endian scalars, then raw SHA-256 (32).
    Filter JSON retains legacy ASCII escaping for v1 compatibility.
    """
    payload = (
        _V2_HEADER
        + key.date_utc.toordinal().to_bytes(3, "big")
        + bytes([_SOURCE_KINDS.index(key.source_kind)])
        + _encode_identifier(key.agent_id)
        + _encode_identifier(key.endpoint_id)
        + _encode_identifier(key.probe_type)
        + bytes.fromhex(_filter_fingerprint(filters))
    )
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_v1(raw_payload: bytes) -> tuple[CursorKey, str]:
    payload = json.loads(raw_payload, object_pairs_hook=_object_without_duplicate_keys)
    if not isinstance(payload, dict) or set(payload) != {"v", "k", "f"}:
        raise ValueError
    if type(payload["v"]) is not int or payload["v"] != 1:
        raise ValueError
    key_values = payload["k"]
    if not isinstance(key_values, list) or len(key_values) != len(_KEY_FIELDS):
        raise ValueError
    fingerprint = payload["f"]
    if not isinstance(fingerprint, str) or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise ValueError
    key = CursorKey.model_validate(dict(zip(_KEY_FIELDS, key_values, strict=True)))
    return key, fingerprint


def _decode_v2(raw_payload: bytes) -> tuple[CursorKey, str]:
    if len(raw_payload) < 52 or raw_payload[:4] != _V2_HEADER:
        raise ValueError
    date_utc = date.fromordinal(int.from_bytes(raw_payload[4:7], "big"))
    source = raw_payload[7]
    if source >= len(_SOURCE_KINDS):
        raise ValueError
    identifiers: list[str] = []
    offset = 8
    for _ in range(3):
        if offset >= len(raw_payload) - 32:
            raise ValueError
        length = raw_payload[offset]
        offset += 1
        end = offset + 3 * length
        if not 1 <= length <= 128 or end > len(raw_payload) - 32:
            raise ValueError
        scalars = [
            int.from_bytes(raw_payload[index : index + 3], "big") for index in range(offset, end, 3)
        ]
        if any(scalar > 0x10FFFF or 0xD800 <= scalar <= 0xDFFF for scalar in scalars):
            raise ValueError
        identifiers.append("".join(chr(scalar) for scalar in scalars))
        offset = end
    if len(raw_payload) - offset != 32:
        raise ValueError
    key = CursorKey(
        date_utc=date_utc,
        agent_id=identifiers[0],
        endpoint_id=identifiers[1],
        source_kind=_SOURCE_KINDS[source],
        probe_type=identifiers[2],
    )
    return key, raw_payload[offset:].hex()


def decode_cursor(token: str, filters: DailyReliabilityFilters) -> CursorKey:
    """Decode a cursor, hiding all malformed-token details from callers."""
    try:
        if not isinstance(token, str) or len(token) > _MAX_CURSOR_LENGTH:
            raise ValueError
        if _URLSAFE_TOKEN_PATTERN.fullmatch(token) is None:
            raise ValueError
        padded_token = token + "=" * (-len(token) % 4)
        raw_payload = base64.b64decode(padded_token, altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw_payload).decode("ascii").rstrip("=") != token:
            raise ValueError
        key, fingerprint = (
            _decode_v2(raw_payload)
            if raw_payload.startswith(_V2_HEADER[:3])
            else _decode_v1(raw_payload)
        )
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
        ValidationError,
    ):
        raise CursorError("invalid cursor") from None

    if fingerprint != _filter_fingerprint(filters):
        raise CursorError("cursor does not match filters")
    return key
