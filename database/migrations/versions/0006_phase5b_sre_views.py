"""Add SRE reporting views, monitoring role, and Docker probe identity.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agents DROP CONSTRAINT agents_agent_role_check;
        ALTER TABLE agents ADD CONSTRAINT agents_agent_role_check
            CHECK (agent_role IN ('wired_reference', 'wifi_observer', 'container_probe'));

        INSERT INTO agents (agent_id, agent_role, display_name)
        VALUES ('container-observer-01', 'container_probe', 'Docker integration probe')
        ON CONFLICT (agent_id) DO UPDATE SET
            agent_role = EXCLUDED.agent_role,
            display_name = EXCLUDED.display_name;

        CREATE VIEW v_sre_agent_status AS
        SELECT
            a.agent_id,
            a.agent_role,
            a.display_name,
            a.enabled,
            heartbeat.event_time AS last_heartbeat_at,
            CASE
                WHEN heartbeat.event_time IS NULL THEN NULL
                ELSE GREATEST(
                    0,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - heartbeat.event_time))
                )
            END AS heartbeat_age_seconds,
            heartbeat.local_queue_depth,
            COALESCE(jsonb_array_length(heartbeat.collection_errors), 0)
                AS collection_error_count
        FROM agents a
        LEFT JOIN LATERAL (
            SELECT h.event_time, h.local_queue_depth, h.collection_errors
            FROM agent_heartbeats h
            WHERE h.agent_id = a.agent_id
            ORDER BY h.event_time DESC, h.event_id DESC
            LIMIT 1
        ) heartbeat ON TRUE;

        CREATE VIEW v_sre_pipeline_status AS
        SELECT
            CURRENT_TIMESTAMP AS observed_at,
            (SELECT MAX(received_at) FROM raw_events) AS last_raw_event_received_at,
            CASE
                WHEN (SELECT MAX(received_at) FROM raw_events) IS NULL THEN NULL
                ELSE GREATEST(
                    0,
                    EXTRACT(EPOCH FROM (
                        CURRENT_TIMESTAMP - (SELECT MAX(received_at) FROM raw_events)
                    ))
                )
            END AS raw_event_age_seconds,
            (SELECT COUNT(*) FROM processing_failures
             WHERE dead_letter_published_at IS NULL) AS pending_dead_letter_count,
            (SELECT COUNT(*) FROM stream_processing_failures)
                AS stream_processing_failure_count,
            (SELECT MAX(completed_at) FROM streaming_query_batches)
                AS last_stream_batch_completed_at,
            (SELECT COUNT(*) FROM network_incidents WHERE status <> 'resolved')
                AS active_incident_count,
            (SELECT COUNT(*) FROM incident_state_events WHERE published_at IS NULL)
                AS pending_incident_publication_count;

        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_monitor') THEN
                CREATE ROLE netpulse_monitor NOLOGIN;
            END IF;
        END $$;
        GRANT pg_monitor TO netpulse_monitor;
        GRANT USAGE ON SCHEMA public TO netpulse_report;
        GRANT SELECT ON v_sre_agent_status, v_sre_pipeline_status TO netpulse_report;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE SELECT ON v_sre_agent_status, v_sre_pipeline_status FROM netpulse_report;
        DROP VIEW IF EXISTS v_sre_pipeline_status;
        DROP VIEW IF EXISTS v_sre_agent_status;
        REVOKE pg_monitor FROM netpulse_monitor;

        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_auth_members
                WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = 'netpulse_monitor')
            ) THEN
                DROP ROLE IF EXISTS netpulse_monitor;
            END IF;
        END $$;

        DELETE FROM agents WHERE agent_id = 'container-observer-01';
        ALTER TABLE agents DROP CONSTRAINT agents_agent_role_check;
        ALTER TABLE agents ADD CONSTRAINT agents_agent_role_check
            CHECK (agent_role IN ('wired_reference', 'wifi_observer'));
        """
    )
