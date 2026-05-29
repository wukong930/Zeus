"""add alert list keyset pagination indexes

Revision ID: 20260529_0050
Revises: 20260528_0049
Create Date: 2026-05-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260529_0050"
down_revision: str | None = "20260528_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_alerts_status_triggered_id",
        "alerts",
        ["status", "triggered_at", "id"],
    )
    op.create_index(
        "ix_alerts_category_triggered_id",
        "alerts",
        ["category", "triggered_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_category_triggered_id", table_name="alerts")
    op.drop_index("ix_alerts_status_triggered_id", table_name="alerts")
