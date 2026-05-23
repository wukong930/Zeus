"""add drift metric query index

Revision ID: 20260503_0025
Revises: 20260503_0024
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0025"
down_revision: str | None = "20260503_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_drift_metrics_computed_at_id",
        "drift_metrics",
        ["computed_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_drift_metrics_computed_at_id", table_name="drift_metrics")
