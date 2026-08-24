"""Add deterministic incident lifecycle state and a durable Kafka outbox.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE network_incidents (
            incident_id UUID PRIMARY KEY,
            incident_key TEXT NOT NULL,
            incident_type TEXT NOT NULL CHECK (
                incident_type IN (
                    'wifi_degradation', 'wifi_outage', 'router_unavailable',
                    'isp_outage', 'dns_failure', 'external_service_failure',
                    'high_latency', 'high_packet_loss', 'agent_offline',
                    'unknown_network_incident'
                )
            ),
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ,
            status TEXT NOT NULL CHECK (
                status IN ('candidate', 'open', 'ongoing', 'recovering', 'resolved')
            ),
            severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
            confidence_score DOUBLE PRECISION NOT NULL
                CHECK (confidence_score >= 0 AND confidence_score <= 1),
            affected_agents JSONB NOT NULL,
            affected_endpoints JSONB NOT NULL,
            evidence JSONB NOT NULL,
            rule_version TEXT NOT NULL,
            peak_latency_ms DOUBLE PRECISION CHECK (peak_latency_ms >= 0),
            maximum_packet_loss_pct DOUBLE PRECISION CHECK (
                maximum_packet_loss_pct >= 0 AND maximum_packet_loss_pct <= 100
            ),
            duration_ms DOUBLE PRECISION NOT NULL CHECK (duration_ms >= 0),
            summary TEXT NOT NULL CHECK (LENGTH(summary) > 0),
            recommended_action TEXT NOT NULL CHECK (LENGTH(recommended_action) > 0),
            state_revision INTEGER NOT NULL CHECK (state_revision > 0),
            positive_observations INTEGER NOT NULL CHECK (positive_observations > 0),
            recovery_observations INTEGER NOT NULL CHECK (recovery_observations >= 0),
            last_observed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (end_time IS NULL OR end_time >= start_time),
            CHECK (
                (status = 'resolved' AND end_time IS NOT NULL)
                OR (status <> 'resolved' AND end_time IS NULL)
            )
        );

        CREATE UNIQUE INDEX uq_network_incidents_active_key
            ON network_incidents(incident_key)
            WHERE status <> 'resolved';
        CREATE INDEX ix_network_incidents_type_time
            ON network_incidents(incident_type, start_time DESC);
        CREATE INDEX ix_network_incidents_status_time
            ON network_incidents(status, last_observed_at DESC);

        CREATE TABLE incident_state_events (
            event_id UUID PRIMARY KEY,
            incident_id UUID NOT NULL REFERENCES network_incidents(incident_id)
                ON DELETE CASCADE,
            state_revision INTEGER NOT NULL CHECK (state_revision > 0),
            status TEXT NOT NULL CHECK (
                status IN ('candidate', 'open', 'ongoing', 'recovering', 'resolved')
            ),
            event_time TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL,
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (incident_id, state_revision)
        );

        CREATE INDEX ix_incident_state_events_pending
            ON incident_state_events(event_time, incident_id, state_revision)
            WHERE published_at IS NULL;

        GRANT SELECT, INSERT, UPDATE, DELETE ON
            network_incidents,
            incident_state_events
        TO netpulse_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS incident_state_events;
        DROP TABLE IF EXISTS network_incidents;
        """
    )
