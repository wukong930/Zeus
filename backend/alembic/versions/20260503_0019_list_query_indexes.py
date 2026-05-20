"""add composite indexes for list query hot paths

Revision ID: 20260503_0019
Revises: 20260503_0018
Create Date: 2026-05-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0019"
down_revision: str | None = "20260503_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_alerts_status_triggered_at", "alerts", ["status", "triggered_at"])
    op.create_index("ix_alerts_category_triggered_at", "alerts", ["category", "triggered_at"])
    op.create_index(
        "ix_recommendations_status_created_at",
        "recommendations",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_recommendations_status_expires_at",
        "recommendations",
        ["status", "expires_at"],
    )
    op.create_index("ix_positions_status_opened_at", "positions", ["status", "opened_at"])
    op.create_index(
        "ix_change_review_queue_status_created_at",
        "change_review_queue",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_change_review_queue_source_created_at",
        "change_review_queue",
        ["source", "created_at"],
    )
    op.create_index(
        "ix_news_events_source_published_at",
        "news_events",
        ["source", "published_at"],
    )
    op.create_index(
        "ix_news_events_event_type_published_at",
        "news_events",
        ["event_type", "published_at"],
    )
    op.create_index(
        "ix_news_events_verification_published_at",
        "news_events",
        ["verification_status", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_events_verification_published_at", table_name="news_events")
    op.drop_index("ix_news_events_event_type_published_at", table_name="news_events")
    op.drop_index("ix_news_events_source_published_at", table_name="news_events")
    op.drop_index("ix_change_review_queue_source_created_at", table_name="change_review_queue")
    op.drop_index("ix_change_review_queue_status_created_at", table_name="change_review_queue")
    op.drop_index("ix_positions_status_opened_at", table_name="positions")
    op.drop_index("ix_recommendations_status_expires_at", table_name="recommendations")
    op.drop_index("ix_recommendations_status_created_at", table_name="recommendations")
    op.drop_index("ix_alerts_category_triggered_at", table_name="alerts")
    op.drop_index("ix_alerts_status_triggered_at", table_name="alerts")
