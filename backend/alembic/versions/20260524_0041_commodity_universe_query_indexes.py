"""add commodity universe query indexes

Revision ID: 20260524_0041
Revises: 20260524_0040
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0041"
down_revision: str | None = "20260524_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_commodity_history_symbol_id", "commodity_history", ["symbol", "id"])
    op.create_index(
        "ix_commodity_history_active_symbol_id",
        "commodity_history",
        ["active_from", "active_to", "symbol", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_commodity_history_active_symbol_id", table_name="commodity_history")
    op.drop_index("ix_commodity_history_symbol_id", table_name="commodity_history")
