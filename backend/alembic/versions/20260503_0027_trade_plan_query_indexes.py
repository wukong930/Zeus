"""add trade plan query indexes

Revision ID: 20260503_0027
Revises: 20260503_0026
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0027"
down_revision: str | None = "20260503_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_event_log_channel_status_created_id",
        "event_log",
        ["channel", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_recommendations_status_expires_created_id",
        "recommendations",
        ["status", "expires_at", "created_at", "id"],
    )
    op.create_index(
        "ix_recommendations_alert_created_id",
        "recommendations",
        ["alert_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_alert_created_id", table_name="recommendations")
    op.drop_index("ix_recommendations_status_expires_created_id", table_name="recommendations")
    op.drop_index("ix_event_log_channel_status_created_id", table_name="event_log")
