"""Add Phase 5A dimensional analytics and read-only views.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-22
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE dim_agent (
            agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
            agent_role TEXT NOT NULL,
            display_name TEXT NOT NULL
        );

        CREATE TABLE dim_endpoint (
            endpoint_id TEXT PRIMARY KEY REFERENCES endpoints(endpoint_id),
            endpoint_type TEXT NOT NULL,
            display_name TEXT NOT NULL
        );

        CREATE TABLE dim_date (date_utc DATE PRIMARY KEY);

        CREATE TABLE dim_probe (
            source_kind TEXT NOT NULL CHECK (
                source_kind IN ('network_measurement', 'service_check')
            ),
            probe_type TEXT NOT NULL,
            PRIMARY KEY (source_kind, probe_type)
        );

        CREATE TABLE fact_reliability_daily (
            date_utc DATE NOT NULL REFERENCES dim_date(date_utc),
            agent_id TEXT NOT NULL REFERENCES dim_agent(agent_id),
            endpoint_id TEXT NOT NULL REFERENCES dim_endpoint(endpoint_id),
            source_kind TEXT NOT NULL,
            probe_type TEXT NOT NULL,
            total_count BIGINT NOT NULL CHECK (total_count > 0),
            success_count BIGINT NOT NULL CHECK (success_count >= 0),
            failure_count BIGINT NOT NULL CHECK (failure_count >= 0),
            latency_sum_ms DOUBLE PRECISION,
            latency_count BIGINT NOT NULL CHECK (latency_count >= 0),
            packet_loss_sum_pct DOUBLE PRECISION,
            packet_loss_count BIGINT NOT NULL CHECK (packet_loss_count >= 0),
            PRIMARY KEY (date_utc, agent_id, endpoint_id, source_kind, probe_type),
            FOREIGN KEY (source_kind, probe_type)
                REFERENCES dim_probe(source_kind, probe_type),
            CHECK (success_count + failure_count = total_count),
            CHECK (latency_count <= total_count AND packet_loss_count <= total_count),
            CHECK ((latency_count = 0) = (latency_sum_ms IS NULL)),
            CHECK ((packet_loss_count = 0) = (packet_loss_sum_pct IS NULL))
        );

        CREATE TABLE fact_incident (
            incident_id UUID PRIMARY KEY,
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ,
            status TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            confidence_score DOUBLE PRECISION NOT NULL,
            duration_ms DOUBLE PRECISION NOT NULL,
            rule_version TEXT NOT NULL,
            state_revision INTEGER NOT NULL CHECK (state_revision > 0)
        );

        CREATE TABLE bridge_incident_agent (
            incident_id UUID NOT NULL REFERENCES fact_incident(incident_id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES dim_agent(agent_id),
            PRIMARY KEY (incident_id, agent_id)
        );

        CREATE TABLE bridge_incident_endpoint (
            incident_id UUID NOT NULL REFERENCES fact_incident(incident_id) ON DELETE CASCADE,
            endpoint_id TEXT NOT NULL REFERENCES dim_endpoint(endpoint_id),
            PRIMARY KEY (incident_id, endpoint_id)
        );

        CREATE TABLE analytics_job_runs (
            run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            from_date DATE,
            through_date DATE,
            is_all BOOLEAN NOT NULL,
            daily_rows BIGINT NOT NULL CHECK (daily_rows >= 0),
            incident_rows BIGINT NOT NULL CHECK (incident_rows >= 0),
            completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (
                (is_all AND from_date IS NULL AND through_date IS NULL)
                OR (
                    NOT is_all AND from_date IS NOT NULL AND through_date IS NOT NULL
                    AND from_date <= through_date
                )
            )
        );

        CREATE VIEW v_daily_probe_reliability AS
        SELECT date_utc, agent_id, endpoint_id, source_kind, probe_type,
               total_count, success_count, failure_count,
               100.0 * success_count / NULLIF(total_count, 0) AS success_rate_pct,
               latency_count, latency_sum_ms,
               latency_sum_ms / NULLIF(latency_count, 0) AS mean_latency_ms,
               packet_loss_count, packet_loss_sum_pct,
               packet_loss_sum_pct / NULLIF(packet_loss_count, 0) AS mean_packet_loss_pct
        FROM fact_reliability_daily;

        CREATE VIEW v_incident_summary AS
        SELECT fi.incident_id, fi.start_time, fi.end_time, fi.status,
               fi.incident_type, fi.severity, fi.confidence_score, fi.duration_ms,
               fi.rule_version, fi.state_revision,
               (SELECT COUNT(*) FROM bridge_incident_agent ba
                WHERE ba.incident_id = fi.incident_id) AS affected_agent_count,
               (SELECT COUNT(*) FROM bridge_incident_endpoint be
                WHERE be.incident_id = fi.incident_id) AS affected_endpoint_count
        FROM fact_incident fi;

        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_report') THEN
                CREATE ROLE netpulse_report NOLOGIN;
            END IF;
        END $$;
        GRANT USAGE ON SCHEMA public TO netpulse_report;
        GRANT SELECT ON v_daily_probe_reliability, v_incident_summary TO netpulse_report;

        GRANT SELECT, INSERT, UPDATE, DELETE ON dim_agent, dim_endpoint, dim_date,
            dim_probe, fact_reliability_daily, fact_incident, bridge_incident_agent,
            bridge_incident_endpoint, analytics_job_runs TO netpulse_app;
        GRANT USAGE, SELECT ON SEQUENCE analytics_job_runs_run_id_seq TO netpulse_app;
        """
    )


def downgrade() -> None:
    """Remove analytics objects; reader membership may need manual removal first."""
    op.execute(
        """
        REVOKE SELECT ON v_daily_probe_reliability, v_incident_summary
            FROM netpulse_report;
        REVOKE USAGE ON SCHEMA public FROM netpulse_report;
        DROP VIEW IF EXISTS v_incident_summary;
        DROP VIEW IF EXISTS v_daily_probe_reliability;
        DROP TABLE IF EXISTS bridge_incident_endpoint;
        DROP TABLE IF EXISTS bridge_incident_agent;
        DROP TABLE IF EXISTS fact_incident;
        DROP TABLE IF EXISTS fact_reliability_daily;
        DROP TABLE IF EXISTS analytics_job_runs;
        DROP TABLE IF EXISTS dim_probe;
        DROP TABLE IF EXISTS dim_date;
        DROP TABLE IF EXISTS dim_endpoint;
        DROP TABLE IF EXISTS dim_agent;

        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_auth_members
                WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = 'netpulse_report')
            ) THEN
                DROP ROLE IF EXISTS netpulse_report;
            END IF;
        END $$;
        """
    )
