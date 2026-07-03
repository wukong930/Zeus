"""add llm budget active lookup index

Revision ID: 20260525_0046
Revises: 20260525_0045
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260525_0046"
down_revision: str | None = "20260525_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_llm_budgets_active_lookup",
        "llm_budgets",
        ["module", "period_start", "status", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_budgets_active_lookup", table_name="llm_budgets")
