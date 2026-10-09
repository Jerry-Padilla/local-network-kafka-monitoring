"""Read-only PostgreSQL reporting snapshot for Tableau exports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

import psycopg

from netpulse_analytics.tableau.models import (
    DailyReliabilitySource,
    IncidentSource,
    PipelineHealthSource,
    TableauSnapshot,
)


class PostgresTableauRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def load_snapshot(self) -> TableauSnapshot:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.transaction(),
        ):
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            daily_rows = connection.execute(
                    """SELECT
                           d.date_utc,
                           d.agent_id,
                           a.agent_role,
                           d.source_kind,
                           d.probe_type,
                           d.total_count,
                           d.success_count,
                           d.failure_count,
                           d.latency_count,
                           d.latency_sum_ms,
                           d.packet_loss_count,
                           d.packet_loss_sum_pct
                       FROM v_daily_probe_reliability d
                       LEFT JOIN v_sre_agent_status a ON a.agent_id = d.agent_id
                       ORDER BY d.date_utc, d.agent_id, d.source_kind, d.probe_type,
                                d.endpoint_id"""
            ).fetchall()
            incident_rows = connection.execute(
                    """SELECT
                           incident_id,
                           incident_type,
                           start_time,
                           end_time,
                           duration_ms,
                           status,
                           severity,
                           confidence_score,
                           rule_version,
                           state_revision,
                           affected_agent_count,
                           affected_endpoint_count
                       FROM v_incident_summary
                       ORDER BY start_time, incident_id"""
            ).fetchall()
            pipeline_rows = connection.execute(
                    """SELECT
                           observed_at,
                           last_raw_event_received_at,
                           raw_event_age_seconds,
                           pending_dead_letter_count,
                           stream_processing_failure_count,
                           last_stream_batch_completed_at,
                           active_incident_count,
                           pending_incident_publication_count
                       FROM v_sre_pipeline_status
                       ORDER BY observed_at"""
            ).fetchall()

        return TableauSnapshot(
            daily_reliability=tuple(self._daily_row(row) for row in daily_rows),
            incidents=tuple(self._incident_row(row) for row in incident_rows),
            pipeline_health=(
                self._pipeline_row(pipeline_rows[0]) if pipeline_rows else None
            ),
        )

    @staticmethod
    def _daily_row(row: tuple[Any, ...]) -> DailyReliabilitySource:
        return DailyReliabilitySource(
            date_utc=cast(date, row[0]),
            agent_id=str(row[1]),
            agent_role=None if row[2] is None else str(row[2]),
            source_kind=str(row[3]),
            measurement_type=str(row[4]),
            total_count=int(row[5]),
            success_count=int(row[6]),
            failure_count=int(row[7]),
            latency_count=int(row[8]),
            latency_sum_ms=None if row[9] is None else float(row[9]),
            packet_loss_count=int(row[10]),
            packet_loss_sum_pct=None if row[11] is None else float(row[11]),
        )

    @staticmethod
    def _incident_row(row: tuple[Any, ...]) -> IncidentSource:
        incident_id = row[0] if isinstance(row[0], UUID) else UUID(str(row[0]))
        return IncidentSource(
            incident_id=incident_id,
            incident_type=str(row[1]),
            start_time=cast(datetime, row[2]),
            end_time=cast(datetime | None, row[3]),
            duration_ms=float(row[4]),
            status=str(row[5]),
            severity=str(row[6]),
            confidence_score=float(row[7]),
            rule_version=str(row[8]),
            state_revision=int(row[9]),
            affected_agent_count=int(row[10]),
            affected_endpoint_count=int(row[11]),
        )

    @staticmethod
    def _pipeline_row(row: tuple[Any, ...]) -> PipelineHealthSource:
        return PipelineHealthSource(
            observed_at=cast(datetime, row[0]),
            last_raw_event_received_at=cast(datetime | None, row[1]),
            raw_event_age_seconds=None if row[2] is None else float(row[2]),
            pending_dead_letter_count=int(row[3]),
            stream_processing_failure_count=int(row[4]),
            last_stream_batch_completed_at=cast(datetime | None, row[5]),
            active_incident_count=int(row[6]),
            pending_incident_publication_count=int(row[7]),
        )
