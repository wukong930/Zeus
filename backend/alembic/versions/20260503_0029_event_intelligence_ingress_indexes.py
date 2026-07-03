"""add event intelligence ingress indexes

Revision ID: 20260503_0029
Revises: 20260503_0028
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0029"
down_revision: str | None = "20260503_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_news_events_published_id",
        "news_events",
        ["published_at", "id"],
    )
    op.create_index(
        "ix_industry_data_type_timestamp_ingested_id",
        "industry_data",
        ["data_type", "timestamp", "ingested_at", "id"],
    )
    op.create_index(
        "ix_signal_track_created_id",
        "signal_track",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_track_created_id", table_name="signal_track")
    op.drop_index("ix_industry_data_type_timestamp_ingested_id", table_name="industry_data")
    op.drop_index("ix_news_events_published_id", table_name="news_events")
