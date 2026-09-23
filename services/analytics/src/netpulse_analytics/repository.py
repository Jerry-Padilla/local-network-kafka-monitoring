"""PostgreSQL-backed transactional analytics refresh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg

from netpulse_analytics.cli import DateSelection

_LOCK_CLASS_ID = 731945
_LOCK_OBJECT_ID = 5


@dataclass(frozen=True, slots=True)
class RefreshResult:
    run_id: int
    daily_rows: int
    incident_rows: int


class PostgresAnalyticsRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def run(self, selection: DateSelection) -> RefreshResult:
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            lock_row = connection.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                (_LOCK_CLASS_ID, _LOCK_OBJECT_ID),
            ).fetchone()
            if lock_row is None or not bool(lock_row[0]):
                raise RuntimeError("analytics refresh already running")
            try:
                with connection.transaction():
                    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    connection.execute("SET LOCAL TIME ZONE 'UTC'")
                    bounds = self._resolve_bounds(connection, selection)
                    self._refresh_dimensions(connection)
                    daily_rows = 0
                    if bounds is not None:
                        daily_rows = self._refresh_daily(connection, *bounds)
                    incident_rows = self._refresh_incidents(connection)
                    run_row = connection.execute(
                        """INSERT INTO analytics_job_runs (
                               from_date, through_date, is_all, daily_rows, incident_rows
                           ) VALUES (%s, %s, %s, %s, %s)
                           RETURNING run_id""",
                        (
                            selection.from_date,
                            selection.through_date,
                            selection.is_all,
                            daily_rows,
                            incident_rows,
                        ),
                    ).fetchone()
                    if run_row is None:
                        raise RuntimeError("analytics run record was not returned")
                    result = RefreshResult(
                        run_id=int(run_row[0]),
                        daily_rows=daily_rows,
                        incident_rows=incident_rows,
                    )
                return result
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    (_LOCK_CLASS_ID, _LOCK_OBJECT_ID),
                )

    def _resolve_bounds(
        self,
        connection: psycopg.Connection[tuple[Any, ...]],
        selection: DateSelection,
    ) -> tuple[date, date] | None:
        if not selection.is_all:
            if selection.from_date is None or selection.through_date is None:
                raise ValueError("explicit analytics range requires both dates")
            return selection.from_date, selection.through_date
        row = connection.execute(
            """SELECT MIN(date_utc), MAX(date_utc)
               FROM (
                   SELECT (event_time AT TIME ZONE 'UTC')::date AS date_utc
                   FROM network_measurements
                   UNION ALL
                   SELECT (event_time AT TIME ZONE 'UTC')::date
                   FROM service_checks
                   UNION ALL
                   SELECT date_utc FROM fact_reliability_daily
               ) dates"""
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            return None
        return row[0], row[1]

    def _refresh_dimensions(self, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        connection.execute(
            """INSERT INTO dim_agent (agent_id, agent_role, display_name)
               SELECT agent_id, agent_role, display_name FROM agents
               ON CONFLICT (agent_id) DO UPDATE SET
                   agent_role = EXCLUDED.agent_role,
                   display_name = EXCLUDED.display_name"""
        )
        connection.execute(
            """INSERT INTO dim_endpoint (endpoint_id, endpoint_type, display_name)
               SELECT endpoint_id, endpoint_type, display_name FROM endpoints
               ON CONFLICT (endpoint_id) DO UPDATE SET
                   endpoint_type = EXCLUDED.endpoint_type,
                   display_name = EXCLUDED.display_name"""
        )
        connection.execute(
            """INSERT INTO dim_probe (source_kind, probe_type)
               SELECT DISTINCT 'network_measurement', measurement_type
               FROM network_measurements
               UNION
               SELECT DISTINCT 'service_check', check_type FROM service_checks
               ON CONFLICT (source_kind, probe_type) DO NOTHING"""
        )

    def _refresh_daily(
        self,
        connection: psycopg.Connection[tuple[Any, ...]],
        from_date: date,
        through_date: date,
    ) -> int:
        parameters = {"from_date": from_date, "through_date": through_date}
        connection.execute(
            """INSERT INTO dim_date (date_utc)
               SELECT day::date
               FROM generate_series(%(from_date)s::date, %(through_date)s::date, '1 day') day
               ON CONFLICT (date_utc) DO NOTHING""",
            parameters,
        )
        connection.execute(
            """DELETE FROM fact_reliability_daily
               WHERE date_utc BETWEEN %(from_date)s AND %(through_date)s""",
            parameters,
        )
        cursor = connection.execute(
            """WITH observations AS (
                   SELECT (nm.event_time AT TIME ZONE 'UTC')::date AS date_utc,
                          nm.agent_id, nm.target_id AS endpoint_id,
                          'network_measurement'::text AS source_kind,
                          nm.measurement_type AS probe_type, nm.success,
                          nm.latency_ms AS latency_ms, nm.packet_loss_pct
                   FROM network_measurements nm
                   WHERE nm.event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
                     AND nm.event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
                   UNION ALL
                   SELECT (sc.event_time AT TIME ZONE 'UTC')::date,
                          sc.agent_id, sc.endpoint_id, 'service_check'::text,
                          sc.check_type, sc.success, sc.total_duration_ms,
                          NULL::double precision
                   FROM service_checks sc
                   WHERE sc.event_time >= (%(from_date)s::date AT TIME ZONE 'UTC')
                     AND sc.event_time < ((%(through_date)s::date + 1) AT TIME ZONE 'UTC')
               )
               INSERT INTO fact_reliability_daily (
                   date_utc, agent_id, endpoint_id, source_kind, probe_type,
                   total_count, success_count, failure_count,
                   latency_sum_ms, latency_count, packet_loss_sum_pct, packet_loss_count
               )
               SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
                      COUNT(*), COUNT(*) FILTER (WHERE success),
                      COUNT(*) FILTER (WHERE NOT success),
                      SUM(latency_ms), COUNT(latency_ms),
                      SUM(packet_loss_pct), COUNT(packet_loss_pct)
               FROM observations
               GROUP BY date_utc, agent_id, endpoint_id, source_kind, probe_type""",
            parameters,
        )
        return cursor.rowcount

    def _refresh_incidents(self, connection: psycopg.Connection[tuple[Any, ...]]) -> int:
        connection.execute("DELETE FROM bridge_incident_agent")
        connection.execute("DELETE FROM bridge_incident_endpoint")
        connection.execute("DELETE FROM fact_incident")
        connection.execute(
            """INSERT INTO fact_incident (
                   incident_id, start_time, end_time, status, incident_type,
                   severity, confidence_score, duration_ms, rule_version, state_revision
               )
               SELECT incident_id, start_time, end_time, status, incident_type,
                      severity, confidence_score, duration_ms, rule_version, state_revision
               FROM network_incidents"""
        )
        connection.execute(
            """INSERT INTO bridge_incident_agent (incident_id, agent_id)
               SELECT DISTINCT ni.incident_id, member.agent_id
               FROM network_incidents ni
               CROSS JOIN LATERAL jsonb_array_elements_text(ni.affected_agents)
                   AS member(agent_id)"""
        )
        connection.execute(
            """INSERT INTO bridge_incident_endpoint (incident_id, endpoint_id)
               SELECT DISTINCT ni.incident_id, member.endpoint_id
               FROM network_incidents ni
               CROSS JOIN LATERAL jsonb_array_elements_text(ni.affected_endpoints)
                   AS member(endpoint_id)"""
        )
        row = connection.execute("SELECT COUNT(*) FROM fact_incident").fetchone()
        return int(row[0]) if row is not None else 0
