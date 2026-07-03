"""add position query indexes

Revision ID: 20260503_0028
Revises: 20260503_0027
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0028"
down_revision: str | None = "20260503_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_positions_status_opened_id",
        "positions",
        ["status", "opened_at", "id"],
    )
    op.create_index(
        "ix_positions_status_data_mode_priority_id",
        "positions",
        ["status", "data_mode", "monitoring_priority", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_positions_status_data_mode_priority_id", table_name="positions")
    op.drop_index("ix_positions_status_opened_id", table_name="positions")
