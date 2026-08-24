"""PostgreSQL snapshots, lifecycle state, and a durable incident outbox."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from netpulse_contracts.models import Incident
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from netpulse_classifier.models import (
    ActiveIncident,
    Finding,
    HeartbeatSummary,
    IncidentStatus,
    IncidentType,
    MeasurementSummary,
    ObservationSnapshot,
    ServiceSummary,
    Severity,
    Transition,
)


class PostgresIncidentRepository:
    """Load bounded observations and persist replay-safe incident transitions."""

    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=3,
            kwargs={"autocommit": False},
            open=False,
        )

    def open(self) -> None:
        self._pool.open(wait=True)

    def close(self) -> None:
        self._pool.close()

    def healthcheck(self) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1").fetchone()
        return bool(row and row[0] == 1)

    def load_snapshot(self, observed_at: datetime, lookback_seconds: int) -> ObservationSnapshot:
        since = observed_at - timedelta(seconds=lookback_seconds)
        with self._pool.connection() as connection:
            measurement_rows = connection.execute(
                """
                SELECT
                    nm.agent_id,
                    a.agent_role,
                    nm.target_id,
                    nm.measurement_type,
                    COUNT(*)::INTEGER,
                    AVG(CASE WHEN nm.success THEN 100.0 ELSE 0.0 END),
                    MAX(nm.latency_ms),
                    AVG(nm.packet_loss_pct),
                    MIN(nm.signal_dbm),
                    AVG(
                        CASE
                            WHEN nm.connected IS TRUE THEN 100.0
                            WHEN nm.connected IS FALSE THEN 0.0
                            ELSE NULL
                        END
                    )
                FROM network_measurements nm
                JOIN agents a ON a.agent_id = nm.agent_id
                WHERE nm.event_time > %s AND nm.event_time <= %s
                GROUP BY nm.agent_id, a.agent_role, nm.target_id, nm.measurement_type
                """,
                (since, observed_at),
            ).fetchall()
            service_rows = connection.execute(
                """
                SELECT
                    sc.agent_id,
                    a.agent_role,
                    sc.endpoint_id,
                    sc.check_type,
                    COUNT(*)::INTEGER,
                    AVG(CASE WHEN sc.success THEN 100.0 ELSE 0.0 END)
                FROM service_checks sc
                JOIN agents a ON a.agent_id = sc.agent_id
                WHERE sc.event_time > %s AND sc.event_time <= %s
                GROUP BY sc.agent_id, a.agent_role, sc.endpoint_id, sc.check_type
                """,
                (since, observed_at),
            ).fetchall()
            heartbeat_rows = connection.execute(
                """
                SELECT a.agent_id, a.agent_role, MAX(ah.event_time)
                FROM agents a
                LEFT JOIN agent_heartbeats ah ON ah.agent_id = a.agent_id
                WHERE a.enabled = TRUE
                GROUP BY a.agent_id, a.agent_role
                """
            ).fetchall()

        return ObservationSnapshot(
            observed_at=observed_at,
            measurements=tuple(
                MeasurementSummary(
                    agent_id=str(row[0]),
                    agent_role=str(row[1]),
                    target_id=str(row[2]),
                    measurement_type=str(row[3]),
                    sample_count=int(row[4]),
                    success_rate_pct=float(row[5]),
                    peak_latency_ms=float(row[6]) if row[6] is not None else None,
                    mean_packet_loss_pct=float(row[7]),
                    weakest_signal_dbm=float(row[8]) if row[8] is not None else None,
                    connected_rate_pct=float(row[9]) if row[9] is not None else None,
                )
                for row in measurement_rows
            ),
            services=tuple(
                ServiceSummary(
                    agent_id=str(row[0]),
                    agent_role=str(row[1]),
                    endpoint_id=str(row[2]),
                    check_type=str(row[3]),
                    sample_count=int(row[4]),
                    success_rate_pct=float(row[5]),
                )
                for row in service_rows
            ),
            heartbeats=tuple(
                HeartbeatSummary(
                    agent_id=str(row[0]),
                    agent_role=str(row[1]),
                    last_event_time=cast(datetime | None, row[2]),
                )
                for row in heartbeat_rows
            ),
        )

    def load_active(self) -> tuple[ActiveIncident, ...]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    incident_id, incident_key, incident_type, start_time, status,
                    state_revision, positive_observations, recovery_observations,
                    severity, confidence_score, affected_agents, affected_endpoints,
                    evidence, peak_latency_ms, maximum_packet_loss_pct, summary,
                    recommended_action
                FROM network_incidents
                WHERE status <> 'resolved'
                ORDER BY start_time, incident_key
                """
            ).fetchall()
        return tuple(self._active_from_row(row) for row in rows)

    def persist_transition(self, transition: Transition, event: Incident) -> None:
        finding = transition.finding
        payload = event.model_dump(mode="json")
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                INSERT INTO network_incidents (
                    incident_id, incident_key, incident_type, start_time, end_time,
                    status, severity, confidence_score, affected_agents,
                    affected_endpoints, evidence, rule_version, peak_latency_ms,
                    maximum_packet_loss_pct, duration_ms, summary,
                    recommended_action, state_revision, positive_observations,
                    recovery_observations, last_observed_at
                ) VALUES (
                    %(incident_id)s, %(incident_key)s, %(incident_type)s,
                    %(start_time)s, %(end_time)s, %(status)s, %(severity)s,
                    %(confidence_score)s, %(affected_agents)s, %(affected_endpoints)s,
                    %(evidence)s, %(rule_version)s, %(peak_latency_ms)s,
                    %(maximum_packet_loss_pct)s, %(duration_ms)s, %(summary)s,
                    %(recommended_action)s, %(state_revision)s,
                    %(positive_observations)s, %(recovery_observations)s,
                    %(last_observed_at)s
                )
                ON CONFLICT (incident_id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    status = EXCLUDED.status,
                    severity = EXCLUDED.severity,
                    confidence_score = EXCLUDED.confidence_score,
                    affected_agents = EXCLUDED.affected_agents,
                    affected_endpoints = EXCLUDED.affected_endpoints,
                    evidence = EXCLUDED.evidence,
                    peak_latency_ms = GREATEST(
                        network_incidents.peak_latency_ms,
                        EXCLUDED.peak_latency_ms
                    ),
                    maximum_packet_loss_pct = GREATEST(
                        network_incidents.maximum_packet_loss_pct,
                        EXCLUDED.maximum_packet_loss_pct
                    ),
                    duration_ms = EXCLUDED.duration_ms,
                    summary = EXCLUDED.summary,
                    recommended_action = EXCLUDED.recommended_action,
                    state_revision = EXCLUDED.state_revision,
                    positive_observations = EXCLUDED.positive_observations,
                    recovery_observations = EXCLUDED.recovery_observations,
                    last_observed_at = EXCLUDED.last_observed_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                {
                    "incident_id": transition.incident_id,
                    "incident_key": finding.incident_key,
                    "incident_type": finding.incident_type,
                    "start_time": transition.start_time,
                    "end_time": transition.end_time,
                    "status": transition.status,
                    "severity": finding.severity,
                    "confidence_score": finding.confidence_score,
                    "affected_agents": Jsonb(list(finding.affected_agents)),
                    "affected_endpoints": Jsonb(list(finding.affected_endpoints)),
                    "evidence": Jsonb(list(finding.evidence)),
                    "rule_version": event.rule_version,
                    "peak_latency_ms": finding.peak_latency_ms,
                    "maximum_packet_loss_pct": finding.maximum_packet_loss_pct,
                    "duration_ms": event.duration_ms,
                    "summary": finding.summary,
                    "recommended_action": finding.recommended_action,
                    "state_revision": transition.state_revision,
                    "positive_observations": transition.positive_observations,
                    "recovery_observations": transition.recovery_observations,
                    "last_observed_at": event.event_time,
                },
            )
            connection.execute(
                """
                INSERT INTO incident_state_events (
                    event_id, incident_id, state_revision, status, event_time, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    transition.incident_id,
                    transition.state_revision,
                    transition.status,
                    event.event_time,
                    Jsonb(payload),
                ),
            )

    def pending_publications(self, limit: int = 100) -> tuple[tuple[UUID, UUID, bytes], ...]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, incident_id, payload::TEXT
                FROM incident_state_events
                WHERE published_at IS NULL
                ORDER BY event_time, incident_id, state_revision
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return tuple((cast(UUID, row[0]), cast(UUID, row[1]), str(row[2]).encode()) for row in rows)

    def mark_published(self, event_id: UUID) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                UPDATE incident_state_events
                SET published_at = CURRENT_TIMESTAMP
                WHERE event_id = %s
                """,
                (event_id,),
            )

    @staticmethod
    def _active_from_row(row: Any) -> ActiveIncident:
        finding = Finding(
            incident_key=str(row[1]),
            incident_type=cast(IncidentType, row[2]),
            severity=cast(Severity, row[8]),
            confidence_score=float(row[9]),
            affected_agents=tuple(str(item) for item in row[10]),
            affected_endpoints=tuple(str(item) for item in row[11]),
            evidence=tuple(cast(dict[str, object], item) for item in row[12]),
            peak_latency_ms=float(row[13]) if row[13] is not None else None,
            maximum_packet_loss_pct=float(row[14]) if row[14] is not None else None,
            summary=str(row[15]),
            recommended_action=str(row[16]),
        )
        return ActiveIncident(
            incident_id=cast(UUID, row[0]),
            incident_key=str(row[1]),
            incident_type=cast(IncidentType, row[2]),
            start_time=cast(datetime, row[3]),
            status=cast(IncidentStatus, row[4]),
            state_revision=int(row[5]),
            positive_observations=int(row[6]),
            recovery_observations=int(row[7]),
            finding=finding,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)
