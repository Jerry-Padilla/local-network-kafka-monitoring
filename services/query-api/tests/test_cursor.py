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
    assert token not in str(exc_info.value)


def test_cursor_round_trip_uses_complete_ordering_key() -> None:
    filters = DailyReliabilityFilters()

    token = encode_cursor(_key(), filters)

    assert decode_cursor(token, filters) == _key()


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


def test_same_date_rows_produce_distinct_cursors() -> None:
    filters = DailyReliabilityFilters()

    first = encode_cursor(_key(probe_type="icmp"), filters)
    second = encode_cursor(_key(probe_type="http"), filters)

    assert first != second
    assert decode_cursor(first, filters) == _key(probe_type="icmp")
    assert decode_cursor(second, filters) == _key(probe_type="http")
