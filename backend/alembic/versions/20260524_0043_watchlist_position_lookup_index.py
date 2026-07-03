"""add watchlist position lookup index

Revision ID: 20260524_0043
Revises: 20260524_0042
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0043"
down_revision: str | None = "20260524_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_watchlist_symbol_pair_category_lookup",
        "watchlist",
        ["symbol1", "symbol2", "category", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_symbol_pair_category_lookup", table_name="watchlist")
