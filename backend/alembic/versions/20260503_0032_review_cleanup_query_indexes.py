"""add review cleanup query indexes

Revision ID: 20260503_0032
Revises: 20260503_0031
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0032"
down_revision: str | None = "20260503_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_alerts_status_expires_id", "alerts", ["status", "expires_at", "id"])
    op.create_index(
        "ix_recommendations_status_expires_id",
        "recommendations",
        ["status", "expires_at", "id"],
    )
    op.create_index(
        "ix_change_review_queue_triage_scan",
        "change_review_queue",
        ["source", "target_table", "status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_change_review_queue_triage_scan", table_name="change_review_queue")
    op.drop_index("ix_recommendations_status_expires_id", table_name="recommendations")
    op.drop_index("ix_alerts_status_expires_id", table_name="alerts")
