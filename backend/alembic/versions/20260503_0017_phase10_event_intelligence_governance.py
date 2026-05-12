"""phase10 event intelligence governance

Revision ID: 20260503_0017
Revises: 20260503_0016
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0017"
down_revision: str | None = "20260503_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_intelligence_audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=True),
        sa.Column("before_status", sa.String(length=30), nullable=True),
        sa.Column("after_status", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_item_id"],
            ["event_intelligence_items.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_event_item_id",
        "event_intelligence_audit_logs",
        ["event_item_id"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_action",
        "event_intelligence_audit_logs",
        ["action"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_actor",
        "event_intelligence_audit_logs",
        ["actor"],
    )
    op.create_index(
        "ix_event_intelligence_audit_logs_created_at",
        "event_intelligence_audit_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_intelligence_audit_logs_created_at",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_index("ix_event_intelligence_audit_logs_actor", table_name="event_intelligence_audit_logs")
    op.drop_index("ix_event_intelligence_audit_logs_action", table_name="event_intelligence_audit_logs")
    op.drop_index(
        "ix_event_intelligence_audit_logs_event_item_id",
        table_name="event_intelligence_audit_logs",
    )
    op.drop_table("event_intelligence_audit_logs")
