"""add watchlist query index

Revision ID: 20260524_0040
Revises: 20260524_0039
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0040"
down_revision: str | None = "20260524_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_watchlist_enabled_category_order",
        "watchlist",
        ["enabled", "category", "priority", "symbol1", "symbol2", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_enabled_category_order", table_name="watchlist")
