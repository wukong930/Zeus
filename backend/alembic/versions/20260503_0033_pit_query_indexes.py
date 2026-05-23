"""add stable pit query indexes

Revision ID: 20260503_0033
Revises: 20260503_0032
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0033"
down_revision: str | None = "20260503_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_market_data_pit_stable",
        "market_data",
        ["symbol", "contract_month", "timestamp", "vintage_at", "id"],
    )
    op.create_index(
        "ix_industry_data_pit_stable",
        "industry_data",
        ["symbol", "data_type", "timestamp", "vintage_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_industry_data_pit_stable", table_name="industry_data")
    op.drop_index("ix_market_data_pit_stable", table_name="market_data")
