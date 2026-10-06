"""Versioned cursor contract for daily reliability pagination."""

import base64
import hashlib
import json
import re
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


def _legacy_payload() -> dict[str, object]:
    return {
        "v": 1,
        "k": ["2026-10-01", "agent-1", "endpoint-1", "network_measurement", "icmp"],
        "f": "84f92d5076424432730ad79e71aef42bf0722952df8118abf83dca47b23326b6",
    }


def _binary_payload() -> bytes:
    # Independently constructed v2 fixture: magic/version, date ordinal, source,
    # three one-scalar identifiers (A/B/C), and the legacy default-filter digest.
    return (
        b"NPC\x02"
        + date(2026, 10, 1).toordinal().to_bytes(3, "big")
        + b"\x00\x01\x00\x00A\x01\x00\x00B\x01\x00\x00C"
        + bytes.fromhex("84f92d5076424432730ad79e71aef42bf0722952df8118abf83dca47b23326b6")
    )


def _binary_token(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _assert_invalid(token: str, filters: DailyReliabilityFilters) -> None:
    with pytest.raises(CursorError) as exc_info:
        decode_cursor(token, filters)
    assert str(exc_info.value) == "invalid cursor"
    if token:
        assert token not in str(exc_info.value)


def _standard_alphabet_token() -> str:
    payload = _legacy_payload()
    for codepoint in range(0x80, 0x800):
        payload["k"] = ["2026-10-01", chr(codepoint), "endpoint-1", "network_measurement", "icmp"]
        serialized = json.dumps(
            payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        standard_token = base64.b64encode(serialized).decode().rstrip("=")
        if "+" in standard_token or "/" in standard_token:
            return standard_token
    raise AssertionError("could not generate a token containing URL-safe Base64 characters")


def _duplicate_key_token(key: str) -> str:
    payload = _legacy_payload()
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


def test_cursor_round_trip_accepts_three_maximum_non_bmp_identifiers() -> None:
    filters = DailyReliabilityFilters()
    key = CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="\U0001f4e1" * 128,
        endpoint_id="\U0001f680" * 128,
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="\U0010ffff" * 128,
    )

    token = encode_cursor(key, filters)

    assert len(token) <= 2048
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
    assert encode_cursor(key, filters) == token
    assert decode_cursor(token, filters) == key


def test_cursor_accepts_legacy_ascii_escaped_unicode_filter_fingerprint() -> None:
    # This fixture uses the original JSON algorithm, independently of production helpers.
    legacy_filters = {
        "from_date": None,
        "through_date": None,
        "agent_id": "agént-\U0001f4e1",
        "endpoint_id": "终点",
        "source_kind": "service_check",
        "probe_type": "\U0001f680",
    }
    fingerprint = hashlib.sha256(
        json.dumps(legacy_filters, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
    ).hexdigest()
    token = _token(
        {
            "v": 1,
            "k": ["2026-10-01", "agént-\U0001f4e1", "终点", "service_check", "\U0001f680"],
            "f": fingerprint,
        }
    )
    filters = DailyReliabilityFilters(
        agent_id=" agént-\U0001f4e1 ",
        endpoint_id=" 终点 ",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type=" \U0001f680 ",
    )

    assert decode_cursor(token, filters) == CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="agént-\U0001f4e1",
        endpoint_id="终点",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type="\U0001f680",
    )


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
            "v": 3,
            "k": ["2026-10-01", "agent-1", "endpoint-1", "network_measurement", "icmp"],
            "f": "0" * 64,
        }
    )

    _assert_invalid(token, filters)


def test_cursor_accepts_independent_v2_fixture() -> None:
    filters = DailyReliabilityFilters()
    token = _binary_token(_binary_payload())
    key = CursorKey(
        date_utc=date(2026, 10, 1),
        agent_id="A",
        endpoint_id="B",
        source_kind=SourceKind.NETWORK_MEASUREMENT,
        probe_type="C",
    )

    assert decode_cursor(token, filters) == key
    assert encode_cursor(key, filters) == token


@pytest.mark.parametrize("end", range(52))
def test_cursor_rejects_truncated_v2_payload(end: int) -> None:
    _assert_invalid(_binary_token(_binary_payload()[:end]), DailyReliabilityFilters())


@pytest.mark.parametrize(
    ("offset", "replacement"),
    [
        (0, b"BAD"),
        (3, b"\x01"),
        (3, b"\x03"),
        (4, b"\x00\x00\x00"),
        (4, b"\xff\xff\xff"),
        (7, b"\x02"),
        (8, b"\x00"),
        (8, b"\x81"),
        (9, b"\x11\x00\x00"),
        (9, b"\x00\xd8\x00"),
        (9, b"\x00\xdf\xff"),
        (9, b"\x00\x00 "),
        (12, b"\x00"),
        (12, b"\x81"),
        (13, b"\x11\x00\x00"),
        (16, b"\x00"),
        (16, b"\x81"),
        (17, b"\x00\xd8\x00"),
    ],
)
def test_cursor_rejects_malformed_v2_fields(offset: int, replacement: bytes) -> None:
    payload = _binary_payload()
    malformed = payload[:offset] + replacement + payload[offset + len(replacement) :]

    _assert_invalid(_binary_token(malformed), DailyReliabilityFilters())


def test_cursor_rejects_extra_v2_bytes() -> None:
    _assert_invalid(_binary_token(_binary_payload() + b"\x00"), DailyReliabilityFilters())


@pytest.mark.parametrize("version", [1, 2])
def test_cursor_rejects_noncanonical_base64_pad_bits(version: int) -> None:
    token = _token(_legacy_payload()) if version == 1 else _binary_token(_binary_payload())
    assert len(token) % 4 in (2, 3)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    alternate = token[:-1] + alphabet[alphabet.index(token[-1]) ^ 1]

    _assert_invalid(alternate, DailyReliabilityFilters())


def test_cursor_rejects_json_with_binary_version() -> None:
    payload = _legacy_payload()
    payload["v"] = 2

    _assert_invalid(_token(payload), DailyReliabilityFilters())


@pytest.mark.parametrize("date_utc", [date.min, date.max])
def test_cursor_round_trips_date_boundaries(date_utc: date) -> None:
    key = _key().model_copy(update={"date_utc": date_utc})
    filters = DailyReliabilityFilters()

    assert decode_cursor(encode_cursor(key, filters), filters) == key


def test_cursor_preserves_stored_identifier_whitespace_and_scalars() -> None:
    key = _key().model_copy(update={"agent_id": " A\x00\u0800\U0001f4e1 "})
    filters = DailyReliabilityFilters()

    assert decode_cursor(encode_cursor(key, filters), filters) == key


def test_cursor_is_stable_for_equivalent_unicode_filters() -> None:
    first = DailyReliabilityFilters(agent_id=" \U0001f4e1 ", probe_type=" é ")
    second = DailyReliabilityFilters(agent_id="\U0001f4e1", probe_type="é")

    token = encode_cursor(_key(), first)

    assert encode_cursor(_key(), second) == token
    assert decode_cursor(token, second) == _key()


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

    _assert_invalid(_standard_alphabet_token(), filters)


@pytest.mark.parametrize("key", ["v", "k", "f"])
def test_cursor_rejects_duplicate_top_level_keys(key: str) -> None:
    filters = DailyReliabilityFilters()

    _assert_invalid(_duplicate_key_token(key), filters)


def test_same_date_rows_produce_distinct_cursors() -> None:
    filters = DailyReliabilityFilters()

    first = encode_cursor(_key(probe_type="icmp"), filters)
    second = encode_cursor(_key(probe_type="http"), filters)

    assert first != second
    assert decode_cursor(first, filters) == _key(probe_type="icmp")
    assert decode_cursor(second, filters) == _key(probe_type="http")
