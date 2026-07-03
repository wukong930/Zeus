"""add indexes for event intelligence query hot paths

Revision ID: 20260503_0021
Revises: 20260503_0020
Create Date: 2026-05-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0021"
down_revision: str | None = "20260503_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_event_intelligence_items_event_timestamp_impact_score",
        "event_intelligence_items",
        ["event_timestamp", "impact_score"],
    )
    op.create_index(
        "ix_event_intelligence_items_status_event_timestamp",
        "event_intelligence_items",
        ["status", "event_timestamp"],
    )
    op.create_index(
        "ix_event_intelligence_items_mechanisms",
        "event_intelligence_items",
        ["mechanisms"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_event_impact_links_event_item_score",
        "event_impact_links",
        ["event_item_id", "impact_score", "confidence"],
    )
    op.create_index(
        "ix_event_impact_links_symbol_score",
        "event_impact_links",
        ["symbol", "impact_score", "confidence"],
    )
    op.create_index(
        "ix_event_impact_links_mechanism_score",
        "event_impact_links",
        ["mechanism", "impact_score", "confidence"],
    )
    op.create_index(
        "ix_event_impact_links_status_score",
        "event_impact_links",
        ["status", "impact_score", "confidence"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_event_item_created_at",
        "event_intelligence_audit_logs",
        ["event_item_id", "created_at"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_action_created_at",
        "event_intelligence_audit_logs",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_intelligence_audit_logs_action_created_at",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index(
        "ix_event_intelligence_audit_logs_event_item_created_at",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index("ix_event_impact_links_status_score", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_mechanism_score", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_symbol_score", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_event_item_score", table_name="event_impact_links")
    op.drop_index("ix_event_intelligence_items_mechanisms", table_name="event_intelligence_items")
    op.drop_index(
        "ix_event_intelligence_items_status_event_timestamp",
        table_name="event_intelligence_items",
    )
    op.drop_index(
        "ix_event_intelligence_items_event_timestamp_impact_score",
        table_name="event_intelligence_items",
    )
