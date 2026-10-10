"""PostgreSQL checks used by the optional Airflow workflow."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

import psycopg

from netpulse_analytics.orchestration.models import (
    DateRange,
    ReconciliationResult,
    ReportingValidation,
    SourceAssessment,
    SourceSnapshot,
)


class PostgresOrchestrationRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def check_database(self) -> None:
        with psycopg.connect(self._database_url) as connection:
            if connection.execute("SELECT 1").fetchone() != (1,):
                raise RuntimeError("database readiness query returned no row")

    @staticmethod
    def _begin_read_only(connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")

    def load_source_snapshot(self, selected: DateRange) -> SourceSnapshot:
        parameters = {"window_start": selected.start, "window_end": selected.end}
        with psycopg.connect(self._database_url) as connection:
            self._begin_read_only(connection)
            row = connection.execute(
                """WITH observations AS (
                       SELECT event_time FROM network_measurements
                       WHERE event_time >= %(window_start)s AND event_time < %(window_end)s
                       UNION ALL
                       SELECT event_time FROM service_checks
                       WHERE event_time >= %(window_start)s AND event_time < %(window_end)s
                   ), relevant_raw AS (
                       SELECT event_time, received_at FROM raw_events
                       WHERE event_type IN ('network.measurement', 'network.service_check')
                         AND event_time >= %(window_start)s AND event_time < %(window_end)s
                   )
                   SELECT
                       (SELECT COUNT(*) FROM observations) AS observation_count,
                       (SELECT COUNT(*) FROM relevant_raw) AS relevant_raw_count,
                       (SELECT COUNT(*) FROM agent_heartbeats
                        WHERE event_time >= %(window_start)s
                          AND event_time < %(window_end)s) AS heartbeat_count,
                       (SELECT COUNT(*) FROM processing_failures
                        WHERE source_topic IN (
                            'network.measurements.raw.v1', 'network.service-checks.raw.v1'
                        ) AND last_failed_at >= %(window_start)s
                          AND last_failed_at < %(window_end)s) AS invalid_count,
                       (SELECT MAX(event_time) FROM observations) AS latest_observation_at,
                       (SELECT MAX(event_time) FROM agent_heartbeats
                        WHERE event_time >= %(window_start)s
                          AND event_time < %(window_end)s) AS latest_heartbeat_at,
                       (SELECT MAX(GREATEST(
                            0, EXTRACT(EPOCH FROM (received_at - event_time))
                        )) FROM relevant_raw) AS maximum_ingestion_delay_seconds""",
                parameters,
            ).fetchone()
        if row is None:
            raise RuntimeError("source quality query returned no row")
        return SourceSnapshot(
            observation_count=int(row[0]),
            relevant_raw_count=int(row[1]),
            heartbeat_count=int(row[2]),
            invalid_count=int(row[3]),
            latest_observation_at=cast(datetime | None, row[4]),
            latest_heartbeat_at=cast(datetime | None, row[5]),
            maximum_ingestion_delay_seconds=None if row[6] is None else float(row[6]),
        )

    def reconcile(self, selected: DateRange) -> ReconciliationResult:
        parameters = {"from_date": selected.from_date, "through_date": selected.through_date}
        with psycopg.connect(self._database_url) as connection:
            self._begin_read_only(connection)
            daily = connection.execute(_DAILY_RECONCILIATION_SQL, parameters).fetchone()
            incidents = connection.execute(_INCIDENT_RECONCILIATION_SQL).fetchone()
        if daily is None or incidents is None:
            raise RuntimeError("reconciliation query returned no row")
        return ReconciliationResult(
            daily_source_rows=int(daily[0]),
            daily_fact_rows=int(daily[1]),
            daily_mismatch_rows=int(daily[2]),
            source_incidents=int(incidents[0]),
            fact_incidents=int(incidents[1]),
            incident_mismatch_rows=int(incidents[2]),
        )

    def reconcile_all(self) -> ReconciliationResult:
        with psycopg.connect(self._database_url) as connection:
            self._begin_read_only(connection)
            bounds = connection.execute(
                """SELECT MIN(date_utc), MAX(date_utc) FROM (
                       SELECT (event_time AT TIME ZONE 'UTC')::date AS date_utc
                       FROM network_measurements
                       UNION ALL
                       SELECT (event_time AT TIME ZONE 'UTC')::date FROM service_checks
                       UNION ALL
                       SELECT date_utc FROM fact_reliability_daily
                   ) available_dates"""
            ).fetchone()
        if bounds is None or bounds[0] is None or bounds[1] is None:
            today = datetime.now(UTC).date()
            return self.reconcile(DateRange(today, today))
        return self.reconcile(DateRange(cast(date, bounds[0]), cast(date, bounds[1])))

    def validate_reporting(
        self,
        selected: DateRange,
        analytics_run_id: int,
    ) -> ReportingValidation:
        parameters = {
            "from_date": selected.from_date,
            "through_date": selected.through_date,
            "run_id": analytics_run_id,
        }
        with psycopg.connect(self._database_url) as connection:
            self._begin_read_only(connection)
            reporting = connection.execute(_REPORTING_VALIDATION_SQL, parameters).fetchone()
            run = connection.execute(
                """SELECT EXISTS (
                       SELECT 1 FROM analytics_job_runs
                       WHERE run_id = %(run_id)s
                         AND from_date = %(from_date)s
                         AND through_date = %(through_date)s
                         AND NOT is_all
                   ) AS run_matches""",
                parameters,
            ).fetchone()
        if reporting is None or run is None:
            raise RuntimeError("reporting validation query returned no row")
        return ReportingValidation(
            reporting_rows=int(reporting[0]),
            duplicate_rows=int(reporting[1]),
            invalid_rows=int(reporting[2]),
            run_matches=bool(run[0]),
        )

    def start_run(
        self,
        run_key: str,
        selected: DateRange,
        assessment: SourceAssessment,
    ) -> None:
        with psycopg.connect(self._database_url) as connection:
            connection.execute(
                """INSERT INTO analytics_orchestration_runs (
                       run_key, from_date, through_date, status, source_status,
                       source_observation_count, attempt_count, started_at, completed_at,
                       analytics_run_id, daily_mismatch_rows, incident_mismatch_rows,
                       failed_task_id, error_type
                   ) VALUES (
                       %(run_key)s, %(from_date)s, %(through_date)s, 'running',
                       %(source_status)s, %(source_observation_count)s, 1,
                       CURRENT_TIMESTAMP, NULL, NULL, NULL, NULL, NULL, NULL
                   )
                   ON CONFLICT (run_key) DO UPDATE SET
                       from_date = EXCLUDED.from_date,
                       through_date = EXCLUDED.through_date,
                       status = 'running',
                       source_status = EXCLUDED.source_status,
                       source_observation_count = EXCLUDED.source_observation_count,
                       attempt_count = analytics_orchestration_runs.attempt_count + 1,
                       started_at = CURRENT_TIMESTAMP,
                       completed_at = NULL,
                       analytics_run_id = NULL,
                       daily_mismatch_rows = NULL,
                       incident_mismatch_rows = NULL,
                       failed_task_id = NULL,
                       error_type = NULL""",
                {
                    "run_key": run_key,
                    "from_date": selected.from_date,
                    "through_date": selected.through_date,
                    "source_status": assessment.status.value,
                    "source_observation_count": assessment.snapshot.observation_count,
                },
            )

    def record_success(
        self,
        run_key: str,
        analytics_run_id: int,
        result: ReconciliationResult,
    ) -> None:
        with psycopg.connect(self._database_url) as connection:
            connection.execute(
                """UPDATE analytics_orchestration_runs
                   SET status = 'success', completed_at = CURRENT_TIMESTAMP,
                       analytics_run_id = %(analytics_run_id)s,
                       daily_mismatch_rows = %(daily_mismatch_rows)s,
                       incident_mismatch_rows = %(incident_mismatch_rows)s,
                       failed_task_id = NULL, error_type = NULL
                   WHERE run_key = %(run_key)s""",
                {
                    "run_key": run_key,
                    "analytics_run_id": analytics_run_id,
                    "daily_mismatch_rows": result.daily_mismatch_rows,
                    "incident_mismatch_rows": result.incident_mismatch_rows,
                },
            )

    def record_failure(self, run_key: str, failed_task_id: str, error_type: str) -> None:
        with psycopg.connect(self._database_url) as connection:
            connection.execute(
                """UPDATE analytics_orchestration_runs
                   SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                       failed_task_id = %(failed_task_id)s,
                       error_type = %(error_type)s
                   WHERE run_key = %(run_key)s""",
                {
                    "run_key": run_key,
                    "failed_task_id": failed_task_id,
                    "error_type": error_type,
                },
            )


_DAILY_RECONCILIATION_SQL = """WITH observations AS (
    SELECT (event_time AT TIME ZONE 'UTC')::date AS date_utc,
           agent_id, target_id AS endpoint_id,
           'network_measurement'::text AS source_kind,
           measurement_type AS probe_type, success, latency_ms, packet_loss_pct
    FROM network_measurements
    WHERE event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
      AND event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
    UNION ALL
    SELECT (event_time AT TIME ZONE 'UTC')::date, agent_id, endpoint_id,
           'service_check'::text, check_type, success, total_duration_ms,
           NULL::double precision
    FROM service_checks
    WHERE event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
      AND event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
), expected AS (
    SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
           COUNT(*) AS total_count,
           COUNT(*) FILTER (WHERE success) AS success_count,
           COUNT(*) FILTER (WHERE NOT success) AS failure_count,
           SUM(latency_ms) AS latency_sum_ms, COUNT(latency_ms) AS latency_count,
           SUM(packet_loss_pct) AS packet_loss_sum_pct,
           COUNT(packet_loss_pct) AS packet_loss_count
    FROM observations
    GROUP BY date_utc, agent_id, endpoint_id, source_kind, probe_type
), actual AS (
    SELECT * FROM fact_reliability_daily
    WHERE date_utc BETWEEN %(from_date)s AND %(through_date)s
), comparison AS (
    SELECT expected.*, actual.date_utc AS actual_date,
           actual.total_count AS actual_total_count,
           actual.success_count AS actual_success_count,
           actual.failure_count AS actual_failure_count,
           actual.latency_sum_ms AS actual_latency_sum_ms,
           actual.latency_count AS actual_latency_count,
           actual.packet_loss_sum_pct AS actual_packet_loss_sum_pct,
           actual.packet_loss_count AS actual_packet_loss_count
    FROM expected FULL OUTER JOIN actual USING (
        date_utc, agent_id, endpoint_id, source_kind, probe_type
    )
)
SELECT (SELECT COUNT(*) FROM expected) AS daily_source_rows,
       (SELECT COUNT(*) FROM actual) AS daily_fact_rows,
       COUNT(*) FILTER (WHERE
           date_utc IS NULL OR actual_date IS NULL
           OR total_count IS DISTINCT FROM actual_total_count
           OR success_count IS DISTINCT FROM actual_success_count
           OR failure_count IS DISTINCT FROM actual_failure_count
           OR latency_sum_ms IS DISTINCT FROM actual_latency_sum_ms
           OR latency_count IS DISTINCT FROM actual_latency_count
           OR packet_loss_sum_pct IS DISTINCT FROM actual_packet_loss_sum_pct
           OR packet_loss_count IS DISTINCT FROM actual_packet_loss_count
       ) AS daily_mismatch_rows
FROM comparison"""

_INCIDENT_RECONCILIATION_SQL = """WITH expected AS (
    SELECT ni.incident_id, ni.status, ni.state_revision,
           jsonb_array_length(ni.affected_agents) AS agent_count,
           jsonb_array_length(ni.affected_endpoints) AS endpoint_count
    FROM network_incidents ni
), actual AS (
    SELECT fi.incident_id, fi.status, fi.state_revision,
           (SELECT COUNT(*) FROM bridge_incident_agent ba
            WHERE ba.incident_id = fi.incident_id) AS agent_count,
           (SELECT COUNT(*) FROM bridge_incident_endpoint be
            WHERE be.incident_id = fi.incident_id) AS endpoint_count
    FROM fact_incident fi
), comparison AS (
    SELECT expected.incident_id, actual.incident_id AS actual_id,
           expected.status, actual.status AS actual_status,
           expected.state_revision, actual.state_revision AS actual_revision,
           expected.agent_count, actual.agent_count AS actual_agent_count,
           expected.endpoint_count, actual.endpoint_count AS actual_endpoint_count
    FROM expected FULL OUTER JOIN actual USING (incident_id)
)
SELECT (SELECT COUNT(*) FROM expected) AS source_incidents,
       (SELECT COUNT(*) FROM actual) AS fact_incidents,
       COUNT(*) FILTER (WHERE
           incident_id IS NULL OR actual_id IS NULL
           OR status IS DISTINCT FROM actual_status
           OR state_revision IS DISTINCT FROM actual_revision
           OR agent_count IS DISTINCT FROM actual_agent_count
           OR endpoint_count IS DISTINCT FROM actual_endpoint_count
       ) AS incident_mismatch_rows
FROM comparison"""

_REPORTING_VALIDATION_SQL = """WITH selected AS (
    SELECT * FROM v_daily_probe_reliability
    WHERE date_utc BETWEEN %(from_date)s AND %(through_date)s
), duplicate_grains AS (
    SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type
    FROM selected
    GROUP BY date_utc, agent_id, endpoint_id, source_kind, probe_type
    HAVING COUNT(*) > 1
)
SELECT COUNT(*) AS reporting_rows,
       (SELECT COUNT(*) FROM duplicate_grains) AS duplicate_rows,
       COUNT(*) FILTER (WHERE
           total_count <> success_count + failure_count
           OR success_rate_pct NOT BETWEEN 0 AND 100
           OR mean_latency_ms < 0
           OR mean_packet_loss_pct NOT BETWEEN 0 AND 100
       ) AS invalid_rows
FROM selected"""
