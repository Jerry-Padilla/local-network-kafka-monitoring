"""Versioned cursor contract for daily reliability pagination."""

import base64
import json
from datetime import date

import pytest
from netpulse_query_api.cursor import CursorError, decode_cursor, encode_cursor
from netpulse_query_api.models import CursorKey, DailyReliabilityFilters, SourceKind


def _key(*, probe_type: str = "icmp") -> CursorKey:
    return CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="agent-1",
        endpoint_id="endpoint-1",
        source_kind=SourceKind.NETWORK_MEASUREMENT,
        probe_type=probe_type,
    )


def _token(payload: object) -> str:
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(serialized).decode().rstrip("=")


def _assert_invalid(token: str, filters: DailyReliabilityFilters) -> None:
    with pytest.raises(CursorError) as exc_info:
        decode_cursor(token, filters)
    assert str(exc_info.value) == "invalid cursor"
    assert token not in str(exc_info.value)


def _standard_alphabet_token(filters: DailyReliabilityFilters) -> str:
    token = encode_cursor(_key(), filters)
    payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    for codepoint in range(0x80, 0x800):
        payload["k"][1] = chr(codepoint)
        serialized = json.dumps(
            payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        standard_token = base64.b64encode(serialized).decode().rstrip("=")
        if "+" in standard_token or "/" in standard_token:
            return standard_token
    raise AssertionError("could not generate a token containing URL-safe Base64 characters")


def _duplicate_key_token(key: str, filters: DailyReliabilityFilters) -> str:
    token = encode_cursor(_key(), filters)
    encoded = token + "=" * (-len(token) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded))
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    duplicate = json.dumps(payload[key], separators=(",", ":"), sort_keys=True)
    serialized = serialized[:-1] + f',"{key}":{duplicate}' + "}"
    return base64.urlsafe_b64encode(serialized.encode()).decode().rstrip("=")


def test_cursor_round_trip_uses_complete_ordering_key() -> None:
    filters = DailyReliabilityFilters()

    token = encode_cursor(_key(), filters)

    assert decode_cursor(token, filters) == _key()


def test_cursor_round_trip_accepts_maximum_non_bmp_identifier() -> None:
    filters = DailyReliabilityFilters()
    key = CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="agent-1",
        endpoint_id="\U0001f4e1" * 128,
        source_kind=SourceKind.NETWORK_MEASUREMENT,
        probe_type="icmp",
    )

    token = encode_cursor(key, filters)

    assert len(token) <= 2048
    assert decode_cursor(token, filters) == key


def test_cursor_is_stable_for_equivalent_filters() -> None:
    first = DailyReliabilityFilters(agent_id=" agent-1 ", probe_type=" icmp ")
    second = DailyReliabilityFilters(agent_id="agent-1", probe_type="icmp")

    assert encode_cursor(_key(), first) == encode_cursor(_key(), second)


def test_cursor_rejects_filter_mismatch() -> None:
    token = encode_cursor(_key(), DailyReliabilityFilters(agent_id="agent-1"))

    with pytest.raises(CursorError, match="^cursor does not match filters$") as exc_info:
        decode_cursor(token, DailyReliabilityFilters(agent_id="agent-2"))
    assert token not in str(exc_info.value)


def test_cursor_rejects_unknown_version() -> None:
    filters = DailyReliabilityFilters()
    token = _token(
        {
            "v": 2,
            "k": ["2026-10-01", "agent-1", "endpoint-1", "network_measurement", "icmp"],
            "f": "0" * 64,
        }
    )

    _assert_invalid(token, filters)


def test_cursor_rejects_oversize_malformed_and_wrong_shape_payloads() -> None:
    filters = DailyReliabilityFilters()
    invalid_tokens = (
        "a" * 2049,
        "not-base64!",
        _token(
            {
                "v": 1,
                "k": ["2026-10-01", "agent-1", "endpoint-1", "network_measurement"],
                "f": "0" * 64,
            }
        ),
        _token(
            {
                "v": 1,
                "k": ["2026-10-01", " ", "endpoint-1", "network_measurement", "icmp"],
                "f": "0" * 64,
            }
        ),
        _token(
            {
                "v": 1,
                "k": ["2026-10-01", "agent-1", "endpoint-1", "network_measurement", "icmp"],
                "f": "0" * 64,
                "extra": True,
            }
        ),
    )

    for token in invalid_tokens:
        _assert_invalid(token, filters)


def test_cursor_rejects_padded_base64() -> None:
    filters = DailyReliabilityFilters()
    token = encode_cursor(_key(), filters)
    padding = "=" * (-len(token) % 4)
    assert padding

    _assert_invalid(token + padding, filters)


def test_cursor_rejects_standard_base64_alphabet() -> None:
    filters = DailyReliabilityFilters()

    _assert_invalid(_standard_alphabet_token(filters), filters)


@pytest.mark.parametrize("key", ["v", "k", "f"])
def test_cursor_rejects_duplicate_top_level_keys(key: str) -> None:
    filters = DailyReliabilityFilters()

    _assert_invalid(_duplicate_key_token(key, filters), filters)


def test_same_date_rows_produce_distinct_cursors() -> None:
    filters = DailyReliabilityFilters()

    first = encode_cursor(_key(probe_type="icmp"), filters)
    second = encode_cursor(_key(probe_type="http"), filters)

    assert first != second
    assert decode_cursor(first, filters) == _key(probe_type="icmp")
    assert decode_cursor(second, filters) == _key(probe_type="http")
