"""Add replay-safe Phase 3 streaming aggregate storage.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE network_window_metrics (
            window_start TIMESTAMPTZ NOT NULL,
            window_end TIMESTAMPTZ NOT NULL,
            window_size_seconds INTEGER NOT NULL
                CHECK (window_size_seconds IN (60, 300, 900, 86400)),
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            target_id TEXT NOT NULL REFERENCES endpoints(endpoint_id),
            measurement_type TEXT NOT NULL
                CHECK (measurement_type IN ('router_ping', 'external_ping', 'wifi_diagnostics')),
            event_count BIGINT NOT NULL CHECK (event_count > 0),
            success_count BIGINT NOT NULL CHECK (success_count >= 0),
            failure_count BIGINT NOT NULL CHECK (failure_count >= 0),
            success_rate_pct DOUBLE PRECISION NOT NULL
                CHECK (success_rate_pct >= 0 AND success_rate_pct <= 100),
            latency_min_ms DOUBLE PRECISION CHECK (latency_min_ms >= 0),
            latency_max_ms DOUBLE PRECISION CHECK (latency_max_ms >= 0),
            latency_mean_ms DOUBLE PRECISION CHECK (latency_mean_ms >= 0),
            latency_stddev_ms DOUBLE PRECISION CHECK (latency_stddev_ms >= 0),
            latency_p50_ms DOUBLE PRECISION CHECK (latency_p50_ms >= 0),
            latency_p95_ms DOUBLE PRECISION CHECK (latency_p95_ms >= 0),
            latency_p99_ms DOUBLE PRECISION CHECK (latency_p99_ms >= 0),
            jitter_mean_ms DOUBLE PRECISION CHECK (jitter_mean_ms >= 0),
            packet_loss_mean_pct DOUBLE PRECISION
                CHECK (packet_loss_mean_pct >= 0 AND packet_loss_mean_pct <= 100),
            ingestion_latency_mean_ms DOUBLE PRECISION
                CHECK (ingestion_latency_mean_ms >= 0),
            calculated_at TIMESTAMPTZ NOT NULL,
            source_batch_id BIGINT NOT NULL CHECK (source_batch_id >= 0),
            PRIMARY KEY (
                window_start,
                window_end,
                window_size_seconds,
                agent_id,
                target_id,
                measurement_type
            ),
            CHECK (window_end > window_start),
            CHECK (success_count + failure_count = event_count)
        );

        CREATE TABLE stream_processing_failures (
            failure_id BIGSERIAL PRIMARY KEY,
            source_topic TEXT NOT NULL,
            source_partition INTEGER NOT NULL CHECK (source_partition >= 0),
            source_offset BIGINT NOT NULL CHECK (source_offset >= 0),
            source_key TEXT,
            original_payload BYTEA,
            validation_errors JSONB NOT NULL,
            first_failed_at TIMESTAMPTZ NOT NULL,
            last_failed_at TIMESTAMPTZ NOT NULL,
            source_batch_id BIGINT NOT NULL CHECK (source_batch_id >= 0),
            UNIQUE (source_topic, source_partition, source_offset)
        );

        CREATE TABLE streaming_query_batches (
            query_name TEXT NOT NULL,
            batch_id BIGINT NOT NULL CHECK (batch_id >= 0),
            output_rows BIGINT NOT NULL CHECK (output_rows >= 0),
            completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (query_name, batch_id)
        );

        CREATE INDEX ix_window_metrics_agent_time
            ON network_window_metrics(agent_id, window_start DESC);
        CREATE INDEX ix_window_metrics_target_time
            ON network_window_metrics(target_id, window_start DESC);
        CREATE INDEX ix_window_metrics_size_time
            ON network_window_metrics(window_size_seconds, window_start DESC);
        CREATE INDEX ix_stream_failures_time
            ON stream_processing_failures(last_failed_at DESC);

        GRANT SELECT, INSERT, UPDATE, DELETE ON
            network_window_metrics,
            stream_processing_failures,
            streaming_query_batches
        TO netpulse_app;
        GRANT USAGE, SELECT ON SEQUENCE stream_processing_failures_failure_id_seq
        TO netpulse_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS streaming_query_batches;
        DROP TABLE IF EXISTS stream_processing_failures;
        DROP TABLE IF EXISTS network_window_metrics;
        """
    )
