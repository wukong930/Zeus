"""add notebook alert query indexes

Revision ID: 20260503_0031
Revises: 20260503_0030
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0031"
down_revision: str | None = "20260503_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_alerts_triggered_id", "alerts", ["triggered_at", "id"])
    op.create_index("ix_alerts_related_research_id", "alerts", ["related_research_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_related_research_id", table_name="alerts")
    op.drop_index("ix_alerts_triggered_id", table_name="alerts")
