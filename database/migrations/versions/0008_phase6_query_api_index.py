"""Index the complete daily reliability API ordering key.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_fact_reliability_daily_api_order
            ON fact_reliability_daily
            (date_utc DESC, agent_id ASC, endpoint_id ASC, source_kind ASC, probe_type ASC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_fact_reliability_daily_api_order;")
