"""Add Airflow orchestration run state and reporting view.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE analytics_orchestration_runs (
            run_key TEXT PRIMARY KEY,
            from_date DATE NOT NULL,
            through_date DATE NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
            source_status TEXT NOT NULL CHECK (source_status IN (
                'healthy', 'delayed', 'legitimately_empty', 'missing', 'stale', 'invalid'
            )),
            source_observation_count BIGINT NOT NULL CHECK (source_observation_count >= 0),
            attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
            analytics_run_id BIGINT REFERENCES analytics_job_runs(run_id) ON DELETE SET NULL,
            daily_mismatch_rows BIGINT CHECK (daily_mismatch_rows >= 0),
            incident_mismatch_rows BIGINT CHECK (incident_mismatch_rows >= 0),
            failed_task_id TEXT,
            error_type TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMPTZ,
            CHECK (from_date <= through_date),
            CHECK ((status = 'running') = (completed_at IS NULL))
        );

        CREATE VIEW v_analytics_workflow_status AS
        SELECT run_key, from_date, through_date, status, source_status,
               source_observation_count, attempt_count, analytics_run_id,
               daily_mismatch_rows, incident_mismatch_rows,
               failed_task_id, error_type, started_at, completed_at,
               EXTRACT(EPOCH FROM (COALESCE(completed_at, CURRENT_TIMESTAMP) - started_at))
                   AS duration_seconds
        FROM analytics_orchestration_runs;

        GRANT SELECT ON v_analytics_workflow_status TO netpulse_report;
        GRANT SELECT, INSERT, UPDATE, DELETE ON analytics_orchestration_runs TO netpulse_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE SELECT ON v_analytics_workflow_status FROM netpulse_report;
        DROP VIEW IF EXISTS v_analytics_workflow_status;
        DROP TABLE IF EXISTS analytics_orchestration_runs;
        """
    )
