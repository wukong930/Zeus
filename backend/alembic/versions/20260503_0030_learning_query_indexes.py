"""add learning query indexes

Revision ID: 20260503_0030
Revises: 20260503_0029
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0030"
down_revision: str | None = "20260503_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_recommendations_created_id",
        "recommendations",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_user_feedback_recorded_id",
        "user_feedback",
        ["recorded_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_feedback_recorded_id", table_name="user_feedback")
    op.drop_index("ix_recommendations_created_id", table_name="recommendations")
