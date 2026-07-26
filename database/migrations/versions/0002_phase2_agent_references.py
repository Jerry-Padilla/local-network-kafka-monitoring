"""Add the second sample external endpoint used by physical agent configs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO endpoints (
            endpoint_id, endpoint_type, display_name, fabricated_sample
        )
        VALUES (
            'public-dns-b',
            'external_ip',
            'Second fabricated public DNS endpoint',
            TRUE
        )
        ON CONFLICT (endpoint_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM endpoints
        WHERE endpoint_id = 'public-dns-b' AND fabricated_sample = TRUE;
        """
    )
