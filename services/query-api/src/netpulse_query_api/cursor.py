"""Encoding and decoding for versioned daily reliability cursors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any

from pydantic import ValidationError

from netpulse_query_api.models import CursorKey, DailyReliabilityFilters

_MAX_CURSOR_LENGTH = 2048
_KEY_FIELDS = ("date_utc", "agent_id", "endpoint_id", "source_kind", "probe_type")
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_URLSAFE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]*\Z")


class CursorError(ValueError):
    """Raised when a pagination cursor cannot be used."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _filter_fingerprint(filters: DailyReliabilityFilters) -> str:
    return hashlib.sha256(_canonical_json(filters.fingerprint_payload())).hexdigest()


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def encode_cursor(key: CursorKey, filters: DailyReliabilityFilters) -> str:
    """Encode the full ordering key and effective-filter fingerprint."""
    payload = {
        "v": 1,
        "k": [
            key.date_utc.isoformat(),
            key.agent_id,
            key.endpoint_id,
            key.source_kind.value,
            key.probe_type,
        ],
        "f": _filter_fingerprint(filters),
    }
    return base64.urlsafe_b64encode(_canonical_json(payload)).decode("ascii").rstrip("=")


def decode_cursor(token: str, filters: DailyReliabilityFilters) -> CursorKey:
    """Decode a cursor, hiding all malformed-token details from callers."""
    try:
        if not isinstance(token, str) or len(token) > _MAX_CURSOR_LENGTH:
            raise ValueError
        if _URLSAFE_TOKEN_PATTERN.fullmatch(token) is None:
            raise ValueError
        padded_token = token + "=" * (-len(token) % 4)
        raw_payload = base64.b64decode(padded_token, altchars=b"-_", validate=True)
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
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
        ValidationError,
    ):
        raise CursorError("invalid cursor") from None

    if payload["f"] != _filter_fingerprint(filters):
        raise CursorError("cursor does not match filters")
    return key
