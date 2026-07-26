"""Create the Phase 1 operational schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agents (
            agent_id TEXT PRIMARY KEY,
            agent_role TEXT NOT NULL
                CHECK (agent_role IN ('wired_reference', 'wifi_observer')),
            display_name TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE endpoints (
            endpoint_id TEXT PRIMARY KEY,
            endpoint_type TEXT NOT NULL
                CHECK (endpoint_type IN ('router', 'external_ip', 'dns', 'http', 'interface')),
            display_name TEXT NOT NULL,
            fabricated_sample BOOLEAN NOT NULL DEFAULT TRUE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE raw_events (
            event_id UUID PRIMARY KEY,
            event_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL CHECK (schema_version > 0),
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            agent_role TEXT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            published_time TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sequence_number BIGINT NOT NULL CHECK (sequence_number >= 0),
            correlation_id UUID,
            source_version TEXT NOT NULL,
            source_topic TEXT NOT NULL,
            source_partition INTEGER NOT NULL CHECK (source_partition >= 0),
            source_offset BIGINT NOT NULL CHECK (source_offset >= 0),
            payload JSONB NOT NULL,
            quality_status TEXT NOT NULL
                CHECK (
                    quality_status IN (
                        'valid', 'suspect', 'invalid', 'duplicate', 'late', 'stale'
                    )
                ),
            UNIQUE (source_topic, source_partition, source_offset)
        );

        CREATE TABLE network_measurements (
            event_id UUID PRIMARY KEY REFERENCES raw_events(event_id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            target_id TEXT NOT NULL REFERENCES endpoints(endpoint_id),
            event_time TIMESTAMPTZ NOT NULL,
            measurement_type TEXT NOT NULL
                CHECK (measurement_type IN ('router_ping', 'external_ping', 'wifi_diagnostics')),
            success BOOLEAN NOT NULL,
            latency_ms DOUBLE PRECISION CHECK (latency_ms >= 0),
            packet_loss_pct DOUBLE PRECISION NOT NULL
                CHECK (packet_loss_pct >= 0 AND packet_loss_pct <= 100),
            jitter_ms DOUBLE PRECISION CHECK (jitter_ms >= 0),
            signal_dbm DOUBLE PRECISION CHECK (signal_dbm >= -120 AND signal_dbm <= 0),
            connected BOOLEAN,
            error_class TEXT,
            error_message TEXT
        );

        CREATE TABLE service_checks (
            event_id UUID PRIMARY KEY REFERENCES raw_events(event_id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            endpoint_id TEXT NOT NULL REFERENCES endpoints(endpoint_id),
            event_time TIMESTAMPTZ NOT NULL,
            check_type TEXT NOT NULL CHECK (check_type IN ('dns', 'http')),
            success BOOLEAN NOT NULL,
            resolver TEXT,
            domain TEXT,
            lookup_duration_ms DOUBLE PRECISION CHECK (lookup_duration_ms >= 0),
            dns_duration_ms DOUBLE PRECISION CHECK (dns_duration_ms >= 0),
            tcp_duration_ms DOUBLE PRECISION CHECK (tcp_duration_ms >= 0),
            tls_duration_ms DOUBLE PRECISION CHECK (tls_duration_ms >= 0),
            ttfb_ms DOUBLE PRECISION CHECK (ttfb_ms >= 0),
            total_duration_ms DOUBLE PRECISION CHECK (total_duration_ms >= 0),
            http_status INTEGER CHECK (http_status >= 100 AND http_status <= 599),
            returned_record_count INTEGER CHECK (returned_record_count >= 0),
            timeout BOOLEAN NOT NULL,
            error_class TEXT
        );

        CREATE TABLE speed_tests (
            event_id UUID PRIMARY KEY REFERENCES raw_events(event_id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            event_time TIMESTAMPTZ NOT NULL,
            provider TEXT NOT NULL,
            server_id TEXT,
            success BOOLEAN NOT NULL,
            download_mbps DOUBLE PRECISION CHECK (download_mbps >= 0),
            upload_mbps DOUBLE PRECISION CHECK (upload_mbps >= 0),
            latency_ms DOUBLE PRECISION CHECK (latency_ms >= 0),
            duration_ms DOUBLE PRECISION NOT NULL CHECK (duration_ms >= 0),
            bytes_transferred BIGINT NOT NULL CHECK (bytes_transferred >= 0),
            error_class TEXT
        );

        CREATE TABLE agent_heartbeats (
            event_id UUID PRIMARY KEY REFERENCES raw_events(event_id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(agent_id),
            event_time TIMESTAMPTZ NOT NULL,
            hostname TEXT NOT NULL,
            agent_version TEXT NOT NULL,
            device_model TEXT,
            os_version TEXT NOT NULL,
            uptime_seconds DOUBLE PRECISION NOT NULL CHECK (uptime_seconds >= 0),
            cpu_temperature_c DOUBLE PRECISION
                CHECK (cpu_temperature_c >= -40 AND cpu_temperature_c <= 150),
            cpu_utilization_pct DOUBLE PRECISION NOT NULL
                CHECK (cpu_utilization_pct >= 0 AND cpu_utilization_pct <= 100),
            memory_utilization_pct DOUBLE PRECISION NOT NULL
                CHECK (memory_utilization_pct >= 0 AND memory_utilization_pct <= 100),
            disk_utilization_pct DOUBLE PRECISION NOT NULL
                CHECK (disk_utilization_pct >= 0 AND disk_utilization_pct <= 100),
            network_interfaces JSONB NOT NULL,
            collection_errors JSONB NOT NULL,
            local_queue_depth INTEGER NOT NULL CHECK (local_queue_depth >= 0)
        );

        CREATE TABLE processing_failures (
            failure_id BIGSERIAL PRIMARY KEY,
            source_topic TEXT NOT NULL,
            source_partition INTEGER NOT NULL CHECK (source_partition >= 0),
            source_offset BIGINT NOT NULL CHECK (source_offset >= 0),
            source_key TEXT,
            original_payload BYTEA NOT NULL,
            error_class TEXT NOT NULL,
            error_message TEXT NOT NULL,
            validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
            attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
            first_failed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_failed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dead_letter_published_at TIMESTAMPTZ,
            UNIQUE (source_topic, source_partition, source_offset)
        );

        CREATE INDEX ix_raw_events_event_time ON raw_events(event_time DESC);
        CREATE INDEX ix_raw_events_agent_time ON raw_events(agent_id, event_time DESC);
        CREATE INDEX ix_raw_events_type_time ON raw_events(event_type, event_time DESC);
        CREATE INDEX ix_measurements_agent_time
            ON network_measurements(agent_id, event_time DESC);
        CREATE INDEX ix_measurements_target_time
            ON network_measurements(target_id, event_time DESC);
        CREATE INDEX ix_service_checks_endpoint_time
            ON service_checks(endpoint_id, event_time DESC);
        CREATE INDEX ix_heartbeats_agent_time
            ON agent_heartbeats(agent_id, event_time DESC);
        CREATE INDEX ix_processing_failures_time
            ON processing_failures(last_failed_at DESC);

        INSERT INTO agents (agent_id, agent_role, display_name)
        VALUES
            ('network-agent-ethernet-01', 'wired_reference', 'Simulated wired reference'),
            ('network-agent-wifi-01', 'wifi_observer', 'Simulated Wi-Fi observer');

        INSERT INTO endpoints (endpoint_id, endpoint_type, display_name)
        VALUES
            ('router', 'router', 'Fabricated local router'),
            ('public-dns-a', 'external_ip', 'Fabricated public DNS endpoint'),
            ('wifi-interface', 'interface', 'Fabricated wireless interface'),
            ('dns-check', 'dns', 'Fabricated DNS check'),
            ('example-service', 'http', 'Fabricated external service');

        GRANT USAGE ON SCHEMA public TO netpulse_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
            TO netpulse_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO netpulse_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO netpulse_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO netpulse_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS processing_failures;
        DROP TABLE IF EXISTS agent_heartbeats;
        DROP TABLE IF EXISTS speed_tests;
        DROP TABLE IF EXISTS service_checks;
        DROP TABLE IF EXISTS network_measurements;
        DROP TABLE IF EXISTS raw_events;
        DROP TABLE IF EXISTS endpoints;
        DROP TABLE IF EXISTS agents;
        """
    )
