from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest
from netpulse_analytics.tableau.models import (
    DailyReliabilitySource,
    IncidentSource,
    PipelineHealthSource,
)
from netpulse_analytics.tableau.repository import PostgresTableauRepository


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class FakeTransaction:
    def __enter__(self) -> FakeTransaction:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    def execute(self, statement: str) -> FakeCursor:
        normalized = " ".join(statement.split())
        self.sql.append(normalized)
        if "v_daily_probe_reliability" in statement:
            return FakeCursor(
                [
                    (
                        date(2026, 10, 8),
                        "wired-01",
                        "wired_reference",
                        "network_measurement",
                        "router_ping",
                        4,
                        3,
                        1,
                        3,
                        36.0,
                        4,
                        2.5,
                    )
                ]
            )
        if "v_incident_summary" in statement:
            return FakeCursor(
                [
                    (
                        UUID("00000000-0000-0000-0000-000000000001"),
                        "router_outage",
                        datetime(2026, 10, 8, 1, tzinfo=UTC),
                        None,
                        1250.0,
                        "active",
                        "critical",
                        0.91,
                        "v1",
                        2,
                        2,
                        1,
                    )
                ]
            )
        if "v_sre_pipeline_status" in statement:
            return FakeCursor(
                [
                    (
                        datetime(2026, 10, 8, 2, tzinfo=UTC),
                        None,
                        None,
                        0,
                        1,
                        None,
                        1,
                        0,
                    )
                ]
            )
        return FakeCursor([])


@pytest.fixture
def fake_connection(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    connection = FakeConnection()
    monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: connection)
    return connection


def test_repository_reads_only_approved_reporting_views_in_one_utc_snapshot(
    fake_connection: FakeConnection,
) -> None:
    snapshot = PostgresTableauRepository("postgresql://example").load_snapshot()

    assert snapshot.daily_reliability == (
        DailyReliabilitySource(
            date_utc=date(2026, 10, 8),
            agent_id="wired-01",
            agent_role="wired_reference",
            source_kind="network_measurement",
            measurement_type="router_ping",
            total_count=4,
            success_count=3,
            failure_count=1,
            latency_count=3,
            latency_sum_ms=36.0,
            packet_loss_count=4,
            packet_loss_sum_pct=2.5,
        ),
    )
    sql = "\n".join(fake_connection.sql)
    assert "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY" in sql
    assert "SET LOCAL TIME ZONE 'UTC'" in sql
    assert "a.agent_id = d.agent_id" in sql
    assert set(re.findall(r"\bv_[a-z_]+\b", sql)) == {
        "v_daily_probe_reliability",
        "v_incident_summary",
        "v_sre_agent_status",
        "v_sre_pipeline_status",
    }
    for operational_table in ("network_measurements", "fact_incident", "agents"):
        assert operational_table not in sql


def test_repository_maps_null_aggregates_and_end_times_without_coercing_to_zero(
    fake_connection: FakeConnection,
) -> None:
    snapshot = PostgresTableauRepository("postgresql://example").load_snapshot()

    assert snapshot.incidents == (
        IncidentSource(
            incident_id=UUID("00000000-0000-0000-0000-000000000001"),
            incident_type="router_outage",
            start_time=datetime(2026, 10, 8, 1, tzinfo=UTC),
            end_time=None,
            duration_ms=1250.0,
            status="active",
            severity="critical",
            confidence_score=0.91,
            rule_version="v1",
            state_revision=2,
            affected_agent_count=2,
            affected_endpoint_count=1,
        ),
    )
    assert snapshot.pipeline_health == PipelineHealthSource(
        observed_at=datetime(2026, 10, 8, 2, tzinfo=UTC),
        last_raw_event_received_at=None,
        raw_event_age_seconds=None,
        pending_dead_letter_count=0,
        stream_processing_failure_count=1,
        last_stream_batch_completed_at=None,
        active_incident_count=1,
        pending_incident_publication_count=0,
    )


def test_repository_orders_every_query_explicitly(fake_connection: FakeConnection) -> None:
    PostgresTableauRepository("postgresql://example").load_snapshot()

    selects = [statement for statement in fake_connection.sql if statement.startswith("SELECT")]
    assert len(selects) == 3
    assert all("ORDER BY" in statement for statement in selects)


def test_repository_propagates_database_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise psycopg.OperationalError("database unavailable")

    monkeypatch.setattr(psycopg, "connect", fail)

    with pytest.raises(psycopg.OperationalError, match="database unavailable"):
        PostgresTableauRepository("postgresql://example").load_snapshot()
