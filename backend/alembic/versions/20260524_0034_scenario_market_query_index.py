"""add scenario market price query index

Revision ID: 20260524_0034
Revises: 20260503_0033
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0034"
down_revision: str | None = "20260503_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_market_data_symbol_timestamp_vintage_id",
        "market_data",
        ["symbol", "timestamp", "vintage_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_data_symbol_timestamp_vintage_id", table_name="market_data")
