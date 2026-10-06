"""Public daily reliability model contract."""

import json
import math
from datetime import date

import pytest
from netpulse_query_api.models import (
    CursorKey,
    DailyReliabilityFilters,
    DailyReliabilityPage,
    DailyReliabilityRow,
    SourceKind,
)
from pydantic import ValidationError


def test_filters_require_paired_ordered_dates_with_maximum_span() -> None:
    for values in (
        {"from_date": date(2026, 1, 1)},
        {"through_date": date(2026, 1, 1)},
        {"from_date": date(2026, 1, 2), "through_date": date(2026, 1, 1)},
        {"from_date": date(2026, 1, 1), "through_date": date(2027, 1, 2)},
    ):
        with pytest.raises(ValidationError):
            DailyReliabilityFilters(**values)

    accepted = DailyReliabilityFilters(from_date=date(2026, 1, 1), through_date=date(2027, 1, 1))
    assert accepted.from_date == date(2026, 1, 1)
    assert accepted.through_date == date(2027, 1, 1)


@pytest.mark.parametrize("field", ["agent_id", "endpoint_id", "probe_type"])
def test_filters_reject_blank_or_overlong_identifiers(field: str) -> None:
    for value in ("   ", "x" * 129):
        with pytest.raises(ValidationError):
            DailyReliabilityFilters(**{field: value})

    filters = DailyReliabilityFilters(**{field: " Ab C "})
    assert getattr(filters, field) == "Ab C"


def test_filters_fingerprint_uses_only_normalized_effective_filters() -> None:
    filters = DailyReliabilityFilters(
        from_date=date(2026, 1, 1),
        through_date=date(2026, 1, 3),
        agent_id=" Agent-1 ",
        endpoint_id="Endpoint-2",
        source_kind=SourceKind.SERVICE_CHECK,
        probe_type=" TCP ",
    )

    assert filters.fingerprint_payload() == {
        "from_date": "2026-01-01",
        "through_date": "2026-01-03",
        "agent_id": "Agent-1",
        "endpoint_id": "Endpoint-2",
        "source_kind": "service_check",
        "probe_type": "TCP",
    }
    assert list(filters.fingerprint_payload()) == [
        "from_date",
        "through_date",
        "agent_id",
        "endpoint_id",
        "source_kind",
        "probe_type",
    ]


def test_filters_reject_unknown_source_kind_and_fields() -> None:
    with pytest.raises(ValidationError):
        DailyReliabilityFilters(source_kind="other")
    with pytest.raises(ValidationError):
        DailyReliabilityFilters(unexpected="value")


def test_page_serializes_iso_dates_nullable_measurements_and_integer_counts() -> None:
    row = DailyReliabilityRow(
        date_utc=date(2026, 10, 1),
        agent_id="Agent-1",
        endpoint_id="Endpoint-2",
        source_kind=SourceKind.NETWORK_MEASUREMENT,
        probe_type="icmp",
        total_count=3,
        success_count=2,
        failure_count=1,
        success_rate_pct=None,
        latency_count=0,
        latency_sum_ms=None,
        mean_latency_ms=None,
        packet_loss_count=0,
        packet_loss_sum_pct=None,
        mean_packet_loss_pct=None,
    )
    page = DailyReliabilityPage(items=[row], next_cursor=None, limit=50)

    payload = json.loads(page.model_dump_json())

    assert payload["limit"] == 50
    assert payload["next_cursor"] is None
    assert payload["items"][0] == {
        "date_utc": "2026-10-01",
        "agent_id": "Agent-1",
        "endpoint_id": "Endpoint-2",
        "source_kind": "network_measurement",
        "probe_type": "icmp",
        "total_count": 3,
        "success_count": 2,
        "failure_count": 1,
        "success_rate_pct": None,
        "latency_count": 0,
        "latency_sum_ms": None,
        "mean_latency_ms": None,
        "packet_loss_count": 0,
        "packet_loss_sum_pct": None,
        "mean_packet_loss_pct": None,
    }
    for count in ("total_count", "success_count", "failure_count", "latency_count"):
        assert isinstance(payload["items"][0][count], int)


def test_rows_reject_nonfinite_aggregates() -> None:
    valid = {
        "date_utc": date(2026, 10, 1),
        "agent_id": "agent",
        "endpoint_id": "endpoint",
        "source_kind": SourceKind.SERVICE_CHECK,
        "probe_type": "http",
        "total_count": 1,
        "success_count": 1,
        "failure_count": 0,
        "success_rate_pct": 100.0,
        "latency_count": 0,
        "latency_sum_ms": None,
        "mean_latency_ms": None,
        "packet_loss_count": 0,
        "packet_loss_sum_pct": None,
        "mean_packet_loss_pct": None,
    }
    for field in (
        "success_rate_pct",
        "latency_sum_ms",
        "mean_latency_ms",
        "packet_loss_sum_pct",
        "mean_packet_loss_pct",
    ):
        with pytest.raises(ValidationError):
            DailyReliabilityRow(**{**valid, field: math.inf})


def test_database_rows_and_cursor_keys_preserve_identifier_whitespace() -> None:
    values = {
        "date_utc": date(2026, 10, 1),
        "agent_id": " agent ",
        "endpoint_id": " endpoint ",
        "source_kind": SourceKind.SERVICE_CHECK,
        "probe_type": " http ",
    }

    key = CursorKey(**values)
    row = DailyReliabilityRow(
        **values,
        total_count=1,
        success_count=1,
        failure_count=0,
        success_rate_pct=100.0,
        latency_count=0,
        latency_sum_ms=None,
        mean_latency_ms=None,
        packet_loss_count=0,
        packet_loss_sum_pct=None,
        mean_packet_loss_pct=None,
    )

    assert (key.agent_id, key.endpoint_id, key.probe_type) == (
        " agent ",
        " endpoint ",
        " http ",
    )
    assert (row.agent_id, row.endpoint_id, row.probe_type) == (
        " agent ",
        " endpoint ",
        " http ",
    )


def test_page_limit_and_cursor_key_are_bounded() -> None:
    for limit in (0, 201):
        with pytest.raises(ValidationError):
            DailyReliabilityPage(items=[], next_cursor=None, limit=limit)
    with pytest.raises(ValidationError):
        CursorKey(
            date_utc=date(2026, 10, 1),
            agent_id=" ",
            endpoint_id="endpoint",
            source_kind=SourceKind.SERVICE_CHECK,
            probe_type="http",
        )
