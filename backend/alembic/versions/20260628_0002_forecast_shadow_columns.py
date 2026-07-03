"""add forecast shadow-tracking columns

Revision ID: 20260628_0002
Revises: 20260628_0001
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0002"
down_revision: str | None = "20260628_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "forecast_records",
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="21"),
    )
    op.add_column("forecast_records", sa.Column("realized_return", sa.Float(), nullable=True))
    op.add_column(
        "forecast_records",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_forecast_records_signal_resolved",
        "forecast_records",
        ["signal", "resolved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_records_signal_resolved", table_name="forecast_records")
    op.drop_column("forecast_records", "resolved_at")
    op.drop_column("forecast_records", "realized_return")
    op.drop_column("forecast_records", "horizon_days")
