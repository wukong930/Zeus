"""add shadow run active query index

Revision ID: 20260524_0038
Revises: 20260524_0037
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0038"
down_revision: str | None = "20260524_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_shadow_runs_active_window_id",
        "shadow_runs",
        ["status", "started_at", "ended_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_shadow_runs_active_window_id", table_name="shadow_runs")
