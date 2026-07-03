"""add event log relay query index

Revision ID: 20260524_0037
Revises: 20260524_0036
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0037"
down_revision: str | None = "20260524_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_event_log_status_created_id",
        "event_log",
        ["status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_log_status_created_id", table_name="event_log")
