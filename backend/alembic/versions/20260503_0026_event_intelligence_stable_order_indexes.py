"""add event intelligence stable order indexes

Revision ID: 20260503_0026
Revises: 20260503_0025
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0026"
down_revision: str | None = "20260503_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_event_intelligence_items_event_timestamp_impact_id",
        "event_intelligence_items",
        ["event_timestamp", "impact_score", "id"],
    )
    op.create_index(
        "ix_event_impact_links_event_item_score_id",
        "event_impact_links",
        ["event_item_id", "impact_score", "confidence", "id"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_event_item_created_at_id",
        "event_intelligence_audit_logs",
        ["event_item_id", "created_at", "id"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_action_created_at_id",
        "event_intelligence_audit_logs",
        ["action", "created_at", "id"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_created_at_id",
        "event_intelligence_audit_logs",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_intelligence_audit_logs_created_at_id",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index(
        "ix_event_intelligence_audit_logs_action_created_at_id",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index(
        "ix_event_intelligence_audit_logs_event_item_created_at_id",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index(
        "ix_event_impact_links_event_item_score_id",
        table_name="event_impact_links",
    )
    op.drop_index(
        "ix_event_intelligence_items_event_timestamp_impact_id",
        table_name="event_intelligence_items",
    )
