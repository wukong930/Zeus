"""phase10 event intelligence engine

Revision ID: 20260503_0016
Revises: 20260503_0015
Create Date: 2026-05-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0016"
down_revision: str | None = "20260503_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "event_intelligence_items",
        _uuid_pk(),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "symbols",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "regions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "mechanisms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "counterevidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("impact_score", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="shadow_review",
            nullable=False,
        ),
        sa.Column(
            "requires_manual_confirmation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("source_reliability", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("freshness_score", sa.Float(), server_default="1", nullable=False),
        sa.Column(
            "source_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", name="uq_event_intelligence_items_source"),
    )
    op.create_index(
        "ix_event_intelligence_items_event_type",
        "event_intelligence_items",
        ["event_type"],
    )
    op.create_index("ix_event_intelligence_items_status", "event_intelligence_items", ["status"])
    op.create_index(
        "ix_event_intelligence_items_event_timestamp",
        "event_intelligence_items",
        ["event_timestamp"],
    )
    op.create_index(
        "ix_event_intelligence_items_symbols",
        "event_intelligence_items",
        ["symbols"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_event_intelligence_items_regions",
        "event_intelligence_items",
        ["regions"],
        postgresql_using="gin",
    )

    op.create_table(
        "event_impact_links",
        _uuid_pk(),
        sa.Column("event_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("region_id", sa.String(length=80), nullable=True),
        sa.Column("mechanism", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("impact_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("horizon", sa.String(length=20), server_default="short", nullable=False),
        sa.Column("rationale", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "counterevidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="shadow_review",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_item_id"],
            ["event_intelligence_items.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "event_item_id",
            "symbol",
            "region_id",
            "mechanism",
            name="uq_event_impact_links_scope",
        ),
    )
    op.create_index("ix_event_impact_links_symbol", "event_impact_links", ["symbol"])
    op.create_index("ix_event_impact_links_region_id", "event_impact_links", ["region_id"])
    op.create_index("ix_event_impact_links_mechanism", "event_impact_links", ["mechanism"])
    op.create_index("ix_event_impact_links_direction", "event_impact_links", ["direction"])
    op.create_index("ix_event_impact_links_status", "event_impact_links", ["status"])
    op.create_index("ix_event_impact_links_confidence", "event_impact_links", ["confidence"])


def downgrade() -> None:
    op.drop_index("ix_event_impact_links_confidence", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_status", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_direction", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_mechanism", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_region_id", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_symbol", table_name="event_impact_links")
    op.drop_table("event_impact_links")

    op.drop_index(
        "ix_event_intelligence_items_regions",
        table_name="event_intelligence_items",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_event_intelligence_items_symbols",
        table_name="event_intelligence_items",
        postgresql_using="gin",
    )
    op.drop_index("ix_event_intelligence_items_event_timestamp", table_name="event_intelligence_items")
    op.drop_index("ix_event_intelligence_items_status", table_name="event_intelligence_items")
    op.drop_index("ix_event_intelligence_items_event_type", table_name="event_intelligence_items")
    op.drop_table("event_intelligence_items")
