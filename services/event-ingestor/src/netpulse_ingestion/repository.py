"""PostgreSQL persistence with event-id and source-offset deduplication."""

from __future__ import annotations

from typing import Any

from netpulse_contracts.models import (
    AgentHeartbeat,
    Event,
    NetworkMeasurement,
    ServiceCheck,
    SpeedTest,
)
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from netpulse_ingestion.processor_types import SourceRecord


class PostgresEventRepository:
    """Persist validated events and rejected source records."""

    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": False},
            open=False,
        )

    def open(self) -> None:
        self._pool.open(wait=True)

    def close(self) -> None:
        self._pool.close()

    def load_reference_ids(self) -> tuple[set[str], set[str]]:
        """Load enabled agent and endpoint allowlists from PostgreSQL."""
        with self._pool.connection() as connection:
            agents = {
                str(row[0])
                for row in connection.execute(
                    "SELECT agent_id FROM agents WHERE enabled = TRUE"
                ).fetchall()
            }
            endpoints = {
                str(row[0])
                for row in connection.execute(
                    "SELECT endpoint_id FROM endpoints WHERE enabled = TRUE"
                ).fetchall()
            }
        return agents, endpoints

    def persist_event(self, event: Event, source: SourceRecord) -> None:
        payload = event.model_dump(mode="json")
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                INSERT INTO raw_events (
                    event_id, event_type, schema_version, agent_id, agent_role,
                    event_time, published_time, sequence_number, correlation_id,
                    source_version, source_topic, source_partition, source_offset,
                    payload, quality_status
                )
                VALUES (
                    %(event_id)s, %(event_type)s, %(schema_version)s, %(agent_id)s,
                    %(agent_role)s, %(event_time)s, %(published_time)s,
                    %(sequence_number)s, %(correlation_id)s, %(source_version)s,
                    %(source_topic)s, %(source_partition)s, %(source_offset)s,
                    %(payload)s, 'valid'
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "schema_version": event.schema_version,
                    "agent_id": event.agent_id,
                    "agent_role": event.agent_role.value,
                    "event_time": event.event_time,
                    "published_time": event.published_time,
                    "sequence_number": event.sequence_number,
                    "correlation_id": event.correlation_id,
                    "source_version": event.source_version,
                    "source_topic": source.topic,
                    "source_partition": source.partition,
                    "source_offset": source.offset,
                    "payload": Jsonb(payload),
                },
            )
            self._persist_typed(connection, event)

    def _persist_typed(self, connection: Any, event: Event) -> None:
        if isinstance(event, NetworkMeasurement):
            connection.execute(
                """
                INSERT INTO network_measurements (
                    event_id, agent_id, target_id, event_time, measurement_type,
                    success, latency_ms, packet_loss_pct, jitter_ms, signal_dbm,
                    connected, error_class, error_message
                )
                VALUES (
                    %(event_id)s, %(agent_id)s, %(target_id)s, %(event_time)s,
                    %(measurement_type)s, %(success)s, %(latency_ms)s,
                    %(packet_loss_pct)s, %(jitter_ms)s, %(signal_dbm)s,
                    %(connected)s, %(error_class)s, %(error_message)s
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.model_dump(),
            )
        elif isinstance(event, ServiceCheck):
            connection.execute(
                """
                INSERT INTO service_checks (
                    event_id, agent_id, endpoint_id, event_time, check_type,
                    success, resolver, domain, lookup_duration_ms, dns_duration_ms,
                    tcp_duration_ms, tls_duration_ms, ttfb_ms, total_duration_ms,
                    http_status, returned_record_count, timeout, error_class
                )
                VALUES (
                    %(event_id)s, %(agent_id)s, %(endpoint_id)s, %(event_time)s,
                    %(check_type)s, %(success)s, %(resolver)s, %(domain)s,
                    %(lookup_duration_ms)s, %(dns_duration_ms)s, %(tcp_duration_ms)s,
                    %(tls_duration_ms)s, %(ttfb_ms)s, %(total_duration_ms)s,
                    %(http_status)s, %(returned_record_count)s, %(timeout)s,
                    %(error_class)s
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.model_dump(),
            )
        elif isinstance(event, SpeedTest):
            connection.execute(
                """
                INSERT INTO speed_tests (
                    event_id, agent_id, event_time, provider, server_id, success,
                    download_mbps, upload_mbps, latency_ms, duration_ms,
                    bytes_transferred, error_class
                )
                VALUES (
                    %(event_id)s, %(agent_id)s, %(event_time)s, %(provider)s,
                    %(server_id)s, %(success)s, %(download_mbps)s, %(upload_mbps)s,
                    %(latency_ms)s, %(duration_ms)s, %(bytes_transferred)s,
                    %(error_class)s
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.model_dump(),
            )
        elif isinstance(event, AgentHeartbeat):
            data = event.model_dump()
            data["network_interfaces"] = Jsonb(data["network_interfaces"])
            data["collection_errors"] = Jsonb(data["collection_errors"])
            connection.execute(
                """
                INSERT INTO agent_heartbeats (
                    event_id, agent_id, event_time, hostname, agent_version,
                    device_model, os_version, uptime_seconds, cpu_temperature_c,
                    cpu_utilization_pct, memory_utilization_pct,
                    disk_utilization_pct, network_interfaces, collection_errors,
                    local_queue_depth
                )
                VALUES (
                    %(event_id)s, %(agent_id)s, %(event_time)s, %(hostname)s,
                    %(agent_version)s, %(device_model)s, %(os_version)s,
                    %(uptime_seconds)s, %(cpu_temperature_c)s,
                    %(cpu_utilization_pct)s, %(memory_utilization_pct)s,
                    %(disk_utilization_pct)s, %(network_interfaces)s,
                    %(collection_errors)s, %(local_queue_depth)s
                )
                ON CONFLICT (event_id) DO NOTHING
                """,
                data,
            )

    def record_failure(
        self,
        source: SourceRecord,
        error_class: str,
        error_message: str,
        validation_errors: list[dict[str, Any]],
    ) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                INSERT INTO processing_failures (
                    source_topic, source_partition, source_offset, source_key,
                    original_payload, error_class, error_message, validation_errors
                )
                VALUES (
                    %(source_topic)s, %(source_partition)s, %(source_offset)s,
                    %(source_key)s, %(original_payload)s, %(error_class)s,
                    %(error_message)s, %(validation_errors)s
                )
                ON CONFLICT (source_topic, source_partition, source_offset)
                DO UPDATE SET
                    attempt_count = processing_failures.attempt_count + 1,
                    error_class = EXCLUDED.error_class,
                    error_message = EXCLUDED.error_message,
                    validation_errors = EXCLUDED.validation_errors,
                    last_failed_at = CURRENT_TIMESTAMP
                """,
                {
                    "source_topic": source.topic,
                    "source_partition": source.partition,
                    "source_offset": source.offset,
                    "source_key": source.key,
                    "original_payload": source.value,
                    "error_class": error_class,
                    "error_message": error_message,
                    "validation_errors": Jsonb(validation_errors),
                },
            )

    def mark_dead_letter_published(self, source: SourceRecord) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                UPDATE processing_failures
                SET dead_letter_published_at = CURRENT_TIMESTAMP
                WHERE source_topic = %(source_topic)s
                  AND source_partition = %(source_partition)s
                  AND source_offset = %(source_offset)s
                """,
                {
                    "source_topic": source.topic,
                    "source_partition": source.partition,
                    "source_offset": source.offset,
                },
            )

    def healthcheck(self) -> bool:
        with self._pool.connection() as connection:
            result = connection.execute("SELECT 1").fetchone()
        return bool(result and result[0] == 1)
