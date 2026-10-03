"""Add the least-privilege Grafana live measurements view.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_network_measurements_event_time
            ON network_measurements (event_time);

        CREATE VIEW v_grafana_live_measurements AS
        SELECT
            event_time,
            agent_id,
            target_id,
            measurement_type,
            success,
            latency_ms,
            packet_loss_pct,
            jitter_ms
        FROM network_measurements;

        GRANT SELECT ON v_grafana_live_measurements TO netpulse_report;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE SELECT ON v_grafana_live_measurements FROM netpulse_report;
        DROP VIEW IF EXISTS v_grafana_live_measurements;
        DROP INDEX IF EXISTS idx_network_measurements_event_time;
        """
    )
