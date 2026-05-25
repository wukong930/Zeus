"""add signal calibration history lookup index

Revision ID: 20260526_0048
Revises: 20260525_0047
Create Date: 2026-05-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260526_0048"
down_revision: str | None = "20260525_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_signal_calibration_history_lookup",
        "signal_calibration",
        ["signal_type", "category", "regime", "effective_from", "computed_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_calibration_history_lookup", table_name="signal_calibration")
