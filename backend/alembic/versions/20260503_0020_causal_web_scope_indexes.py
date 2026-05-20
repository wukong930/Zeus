"""add indexes for scoped causal web queries

Revision ID: 20260503_0020
Revises: 20260503_0019
Create Date: 2026-05-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0020"
down_revision: str | None = "20260503_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_alerts_related_assets",
        "alerts",
        ["related_assets"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_market_data_symbol_ingested_at",
        "market_data",
        ["symbol", "ingested_at"],
    )
    op.create_index(
        "ix_industry_data_symbol_ingested_at",
        "industry_data",
        ["symbol", "ingested_at"],
    )
    op.create_index(
        "ix_signal_track_category_created_at",
        "signal_track",
        ["category", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_track_category_created_at", table_name="signal_track")
    op.drop_index("ix_industry_data_symbol_ingested_at", table_name="industry_data")
    op.drop_index("ix_market_data_symbol_ingested_at", table_name="market_data")
    op.drop_index("ix_alerts_related_assets", table_name="alerts")
