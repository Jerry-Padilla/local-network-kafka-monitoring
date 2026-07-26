"""Bounded, idempotent PostgreSQL sinks for Spark micro-batches."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

METRIC_COLUMNS = (
    "window_start",
    "window_end",
    "window_size_seconds",
    "agent_id",
    "target_id",
    "measurement_type",
    "event_count",
    "success_count",
    "failure_count",
    "success_rate_pct",
    "latency_min_ms",
    "latency_max_ms",
    "latency_mean_ms",
    "latency_stddev_ms",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "jitter_mean_ms",
    "packet_loss_mean_pct",
    "ingestion_latency_mean_ms",
    "calculated_at",
)

METRIC_UPSERT = """
    INSERT INTO network_window_metrics (
        window_start, window_end, window_size_seconds, agent_id, target_id,
        measurement_type, event_count, success_count, failure_count,
        success_rate_pct, latency_min_ms, latency_max_ms, latency_mean_ms,
        latency_stddev_ms, latency_p50_ms, latency_p95_ms, latency_p99_ms,
        jitter_mean_ms, packet_loss_mean_pct, ingestion_latency_mean_ms,
        calculated_at, source_batch_id
    ) VALUES (
        %(window_start)s, %(window_end)s, %(window_size_seconds)s, %(agent_id)s,
        %(target_id)s, %(measurement_type)s, %(event_count)s, %(success_count)s,
        %(failure_count)s, %(success_rate_pct)s, %(latency_min_ms)s,
        %(latency_max_ms)s, %(latency_mean_ms)s, %(latency_stddev_ms)s,
        %(latency_p50_ms)s, %(latency_p95_ms)s, %(latency_p99_ms)s,
        %(jitter_mean_ms)s, %(packet_loss_mean_pct)s,
        %(ingestion_latency_mean_ms)s, %(calculated_at)s, %(source_batch_id)s
    )
    ON CONFLICT (
        window_start, window_end, window_size_seconds, agent_id, target_id,
        measurement_type
    ) DO UPDATE SET
        event_count = EXCLUDED.event_count,
        success_count = EXCLUDED.success_count,
        failure_count = EXCLUDED.failure_count,
        success_rate_pct = EXCLUDED.success_rate_pct,
        latency_min_ms = EXCLUDED.latency_min_ms,
        latency_max_ms = EXCLUDED.latency_max_ms,
        latency_mean_ms = EXCLUDED.latency_mean_ms,
        latency_stddev_ms = EXCLUDED.latency_stddev_ms,
        latency_p50_ms = EXCLUDED.latency_p50_ms,
        latency_p95_ms = EXCLUDED.latency_p95_ms,
        latency_p99_ms = EXCLUDED.latency_p99_ms,
        jitter_mean_ms = EXCLUDED.jitter_mean_ms,
        packet_loss_mean_pct = EXCLUDED.packet_loss_mean_pct,
        ingestion_latency_mean_ms = EXCLUDED.ingestion_latency_mean_ms,
        calculated_at = EXCLUDED.calculated_at,
        source_batch_id = EXCLUDED.source_batch_id
"""

FAILURE_UPSERT = """
    INSERT INTO stream_processing_failures (
        source_topic, source_partition, source_offset, source_key,
        original_payload, validation_errors, first_failed_at, last_failed_at,
        source_batch_id
    ) VALUES (
        %(source_topic)s, %(source_partition)s, %(source_offset)s, %(source_key)s,
        %(original_payload)s, %(validation_errors)s, %(failed_at)s, %(failed_at)s,
        %(source_batch_id)s
    )
    ON CONFLICT (source_topic, source_partition, source_offset) DO UPDATE SET
        validation_errors = EXCLUDED.validation_errors,
        last_failed_at = EXCLUDED.last_failed_at,
        source_batch_id = EXCLUDED.source_batch_id
"""


class PostgresStreamingSink:
    """Persist small aggregate/reject micro-batches with replay-safe keys."""

    def __init__(self, database_url: str, maximum_rows: int) -> None:
        self._database_url = database_url
        self._maximum_rows = maximum_rows

    def write_metrics(self, batch: Any, batch_id: int) -> None:
        rows = self._bounded_rows(batch)
        values = [
            {
                **{column: _normalize(row.get(column)) for column in METRIC_COLUMNS},
                "source_batch_id": batch_id,
            }
            for row in rows
        ]
        self._write(values, METRIC_UPSERT, "window-metrics", batch_id)

    def write_failures(self, batch: Any, batch_id: int) -> None:
        rows = self._bounded_rows(batch)
        values = [
            {
                "source_topic": row["source_topic"],
                "source_partition": row["source_partition"],
                "source_offset": row["source_offset"],
                "source_key": row["source_key"],
                "original_payload": row["original_payload"],
                "validation_errors": Jsonb(row["validation_errors"]),
                "failed_at": _normalize(row["failed_at"]),
                "source_batch_id": batch_id,
            }
            for row in rows
        ]
        self._write(values, FAILURE_UPSERT, "invalid-measurements", batch_id)

    def _bounded_rows(self, batch: Any) -> list[dict[str, Any]]:
        limited = batch.limit(self._maximum_rows + 1).collect()
        if len(limited) > self._maximum_rows:
            raise RuntimeError("micro-batch output exceeded maximum configured output rows")
        return [row.asDict(recursive=True) for row in limited]

    def _write(
        self,
        rows: list[dict[str, Any]],
        statement: str,
        query_name: str,
        batch_id: int,
    ) -> None:
        with psycopg.connect(self._database_url) as connection:
            if rows:
                with connection.cursor() as cursor:
                    cursor.executemany(statement, rows)
            connection.execute(
                """
                INSERT INTO streaming_query_batches (
                    query_name, batch_id, output_rows
                ) VALUES (%s, %s, %s)
                ON CONFLICT (query_name, batch_id) DO UPDATE SET
                    output_rows = EXCLUDED.output_rows,
                    completed_at = CURRENT_TIMESTAMP
                """,
                (query_name, batch_id, len(rows)),
            )


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
