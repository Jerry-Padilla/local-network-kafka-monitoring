from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from netpulse_analytics.tableau.models import (
    DailyReliabilitySource,
    IncidentSource,
    PipelineHealthSource,
    TableauSnapshot,
)
from netpulse_analytics.tableau.transform import build_export_bundle, pseudonymize_agent


def _daily(
    *,
    date_utc: date = date(2026, 10, 8),
    agent_id: str = "agent-a",
    agent_role: str | None = "wired_reference",
    source_kind: str = "network_measurement",
    measurement_type: str = "router_ping",
    total_count: int = 2,
    success_count: int = 2,
    failure_count: int = 0,
    latency_count: int = 2,
    latency_sum_ms: float | None = 20.0,
    packet_loss_count: int = 2,
    packet_loss_sum_pct: float | None = 0.0,
) -> DailyReliabilitySource:
    return DailyReliabilitySource(
        date_utc=date_utc,
        agent_id=agent_id,
        agent_role=agent_role,
        source_kind=source_kind,
        measurement_type=measurement_type,
        total_count=total_count,
        success_count=success_count,
        failure_count=failure_count,
        latency_count=latency_count,
        latency_sum_ms=latency_sum_ms,
        packet_loss_count=packet_loss_count,
        packet_loss_sum_pct=packet_loss_sum_pct,
    )


def _incident(
    *,
    incident_id: str = "00000000-0000-0000-0000-000000000001",
    incident_type: str = "router_outage",
    start_time: datetime = datetime(2026, 10, 8, 1, tzinfo=UTC),
    end_time: datetime | None = None,
) -> IncidentSource:
    return IncidentSource(
        incident_id=UUID(incident_id),
        incident_type=incident_type,
        start_time=start_time,
        end_time=end_time,
        duration_ms=1250.0,
        status="active",
        severity="critical",
        confidence_score=0.91,
        rule_version="v1",
        state_revision=2,
        affected_agent_count=2,
        affected_endpoint_count=1,
    )


def _pipeline(
    *,
    observed_at: datetime = datetime(2026, 10, 8, 2, tzinfo=UTC),
) -> PipelineHealthSource:
    return PipelineHealthSource(
        observed_at=observed_at,
        last_raw_event_received_at=datetime(2026, 10, 8, 1, 59, 30, tzinfo=UTC),
        raw_event_age_seconds=30.0,
        pending_dead_letter_count=0,
        stream_processing_failure_count=1,
        last_stream_batch_completed_at=None,
        active_incident_count=1,
        pending_incident_publication_count=0,
    )


def test_daily_reliability_has_exact_columns_and_logical_sort_order() -> None:
    snapshot = TableauSnapshot(
        daily_reliability=(
            _daily(date_utc=date(2026, 10, 9), agent_id="agent-a"),
            _daily(date_utc=date(2026, 10, 8), agent_id="agent-a"),
            _daily(date_utc=date(2026, 10, 8), agent_id="agent-b"),
        )
    )

    dataset = build_export_bundle(snapshot).datasets["daily_reliability.csv"]

    assert dataset.columns == (
        "date_utc",
        "agent_key",
        "agent_role",
        "source_kind",
        "measurement_type",
        "total_probes",
        "successful_probes",
        "failed_probes",
        "success_rate_pct",
        "average_latency_ms",
        "average_packet_loss_pct",
    )
    assert [(row[0], row[1]) for row in dataset.rows] == [
        ("2026-10-08", "agent_0b62e3903e31"),
        ("2026-10-08", "agent_4d61eabb2c3e"),
        ("2026-10-09", "agent_4d61eabb2c3e"),
    ]


def test_daily_reliability_aggregates_endpoint_rows_with_weighted_metrics() -> None:
    snapshot = TableauSnapshot(
        daily_reliability=(
            _daily(),
            _daily(
                total_count=8,
                success_count=4,
                failure_count=4,
                latency_count=4,
                latency_sum_ms=100.0,
                packet_loss_count=8,
                packet_loss_sum_pct=20.0,
            ),
        )
    )

    row = build_export_bundle(snapshot).datasets["daily_reliability.csv"].rows[0]

    assert row == (
        "2026-10-08",
        "agent_4d61eabb2c3e",
        "wired_reference",
        "network_measurement",
        "router_ping",
        10,
        6,
        4,
        60.0,
        20.0,
        2.0,
    )


def test_daily_reliability_emits_empty_fields_for_unmeasured_latency_and_loss() -> None:
    snapshot = TableauSnapshot(
        daily_reliability=(
            _daily(
                latency_count=0,
                latency_sum_ms=None,
                packet_loss_count=0,
                packet_loss_sum_pct=None,
            ),
        )
    )

    row = build_export_bundle(snapshot).datasets["daily_reliability.csv"].rows[0]

    assert row[-2:] == (None, None)


def test_empty_daily_snapshot_produces_header_only_daily_and_agent_datasets() -> None:
    bundle = build_export_bundle(TableauSnapshot())

    assert bundle.datasets["daily_reliability.csv"].rows == ()
    assert bundle.datasets["agent_performance.csv"].rows == ()


def test_incidents_have_exact_columns_utc_timestamps_and_stable_order() -> None:
    later = _incident(
        incident_id="00000000-0000-0000-0000-000000000002",
        start_time=datetime(2026, 10, 8, 3, tzinfo=UTC),
    )
    earlier = _incident(
        end_time=datetime(2026, 10, 8, 1, 0, 1, 500000, tzinfo=UTC),
    )

    dataset = build_export_bundle(
        TableauSnapshot(incidents=(later, earlier))
    ).datasets["incidents.csv"]

    assert dataset.columns == (
        "incident_id",
        "incident_type",
        "start_time_utc",
        "end_time_utc",
        "duration_ms",
        "status",
        "severity",
        "confidence_score",
        "rule_version",
        "state_revision",
        "affected_agent_count",
        "affected_endpoint_count",
    )
    assert [row[0] for row in dataset.rows] == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]
    assert dataset.rows[0][2:4] == (
        "2026-10-08T01:00:00Z",
        "2026-10-08T01:00:01.500000Z",
    )


def test_pipeline_health_has_exact_columns_and_utc_timestamps() -> None:
    dataset = build_export_bundle(
        TableauSnapshot(pipeline_health=_pipeline())
    ).datasets["pipeline_health.csv"]

    assert dataset.columns == (
        "observed_at_utc",
        "last_raw_event_received_at_utc",
        "raw_event_age_seconds",
        "pending_dead_letter_count",
        "stream_processing_failure_count",
        "last_stream_batch_completed_at_utc",
        "active_incident_count",
        "pending_incident_publication_count",
    )
    assert dataset.rows == (
        (
            "2026-10-08T02:00:00Z",
            "2026-10-08T01:59:30Z",
            30.0,
            0,
            1,
            None,
            1,
            0,
        ),
    )


def test_non_utc_aware_timestamp_is_converted_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    incident = _incident(start_time=datetime(2026, 10, 8, 3, tzinfo=plus_two))

    row = build_export_bundle(TableauSnapshot(incidents=(incident,))).datasets[
        "incidents.csv"
    ].rows[0]

    assert row[2] == "2026-10-08T01:00:00Z"


def test_naive_timestamp_is_rejected() -> None:
    incident = _incident(start_time=datetime(2026, 10, 8, 1))

    with pytest.raises(ValueError, match="timezone-aware"):
        build_export_bundle(TableauSnapshot(incidents=(incident,)))


def test_incident_timestamp_validation_precedes_sorting() -> None:
    aware = _incident()
    naive = _incident(
        incident_id="00000000-0000-0000-0000-000000000002",
        start_time=datetime(2026, 10, 8, 2),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_export_bundle(TableauSnapshot(incidents=(aware, naive)))


def test_equal_duplicate_incidents_collapse_but_conflicts_raise() -> None:
    incident = _incident()
    equal_bundle = build_export_bundle(TableauSnapshot(incidents=(incident, incident)))

    assert len(equal_bundle.datasets["incidents.csv"].rows) == 1

    conflicting = replace(incident, severity="warning")
    with pytest.raises(ValueError, match="conflicting duplicate incident"):
        build_export_bundle(TableauSnapshot(incidents=(incident, conflicting)))


def test_agent_keys_are_stable_namespaced_digests_and_raw_identifiers_never_appear() -> None:
    first = pseudonymize_agent("agent-a")
    repeated = pseudonymize_agent("agent-a")
    second = pseudonymize_agent("agent-b")

    assert first == repeated == "agent_4d61eabb2c3e"
    assert second != first
    assert re.fullmatch(r"agent_[0-9a-f]{12}", first)

    bundle = build_export_bundle(
        TableauSnapshot(daily_reliability=(_daily(agent_id="private-home-agent"),))
    )
    serialized = repr(bundle.datasets)
    assert "private-home-agent" not in serialized
    for forbidden in ("display_name", "endpoint_id", "target_id", "ssid", "bssid"):
        assert forbidden not in serialized.lower()


def test_export_bundle_contains_only_four_expected_filenames() -> None:
    bundle = build_export_bundle(TableauSnapshot())

    assert set(bundle.datasets) == {
        "daily_reliability.csv",
        "incidents.csv",
        "agent_performance.csv",
        "pipeline_health.csv",
    }
