"""add news event list keyset pagination indexes

Revision ID: 20260529_0051
Revises: 20260529_0050
Create Date: 2026-05-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260529_0051"
down_revision: str | None = "20260529_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_news_events_source_published_id",
        "news_events",
        ["source", "published_at", "id"],
    )
    op.create_index(
        "ix_news_events_event_type_published_id",
        "news_events",
        ["event_type", "published_at", "id"],
    )
    op.create_index(
        "ix_news_events_verification_published_id",
        "news_events",
        ["verification_status", "published_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_events_verification_published_id", table_name="news_events")
    op.drop_index("ix_news_events_event_type_published_id", table_name="news_events")
    op.drop_index("ix_news_events_source_published_id", table_name="news_events")
