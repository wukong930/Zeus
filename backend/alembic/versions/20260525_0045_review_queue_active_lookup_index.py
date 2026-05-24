"""add review queue active lookup index

Revision ID: 20260525_0045
Revises: 20260524_0044
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260525_0045"
down_revision: str | None = "20260524_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_change_review_queue_active_lookup",
        "change_review_queue",
        ["source", "target_table", "target_key", "status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_change_review_queue_active_lookup", table_name="change_review_queue")
