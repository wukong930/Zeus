"""add indexes for runtime heartbeat queries

Revision ID: 20260503_0022
Revises: 20260503_0021
Create Date: 2026-05-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0022"
down_revision: str | None = "20260503_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_signal_track_created_at", "signal_track", ["created_at"])
    op.create_index(
        "ix_signal_track_outcome_created_at",
        "signal_track",
        ["outcome", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_track_outcome_created_at", table_name="signal_track")
    op.drop_index("ix_signal_track_created_at", table_name="signal_track")
