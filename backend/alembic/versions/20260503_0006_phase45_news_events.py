"""phase4.5 news events and vector search

Revision ID: 20260503_0006
Revises: 20260503_0005
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0006"
down_revision: str | None = "20260503_0005"
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
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "news_events",
        _uuid_pk(),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("raw_url", sa.Text()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("affected_symbols", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("time_horizon", sa.String(length=20), nullable=False),
        sa.Column("llm_confidence", sa.Float(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="single_source",
        ),
        sa.Column(
            "requires_manual_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.Column("extraction_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_news_events_source", "news_events", ["source"])
    op.create_index("ix_news_events_published_at", "news_events", ["published_at"])
    op.create_index("ix_news_events_event_type", "news_events", ["event_type"])
    op.create_index("ix_news_events_direction", "news_events", ["direction"])
    op.create_index("ix_news_events_severity", "news_events", ["severity"])
    op.create_index("ix_news_events_dedup_hash", "news_events", ["dedup_hash"], unique=True)
    op.create_index(
        "ix_news_events_affected_symbols",
        "news_events",
        ["affected_symbols"],
        postgresql_using="gin",
    )

    op.execute(
        """
        CREATE TABLE vector_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            chunk_type varchar(40) NOT NULL,
            source_id uuid,
            content_text text NOT NULL,
            embedding vector(1024),
            embedding_model varchar(80),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            quality_status varchar(20) NOT NULL DEFAULT 'unverified',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index("ix_vector_chunks_chunk_type", "vector_chunks", ["chunk_type"])
    op.create_index("ix_vector_chunks_source_id", "vector_chunks", ["source_id"])
    op.create_index("ix_vector_chunks_quality_status", "vector_chunks", ["quality_status"])
    op.create_index("ix_vector_chunks_created_at", "vector_chunks", ["created_at"])
    op.create_index(
        "ix_vector_chunks_metadata",
        "vector_chunks",
        ["metadata"],
        postgresql_using="gin",
    )
    op.execute(
        """
        CREATE INDEX ix_vector_chunks_content_tsv
        ON vector_chunks
        USING gin (to_tsvector('simple', content_text))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_vector_chunks_embedding_hnsw
        ON vector_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_vector_chunks_embedding_hnsw", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_content_tsv", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_metadata", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_created_at", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_quality_status", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_source_id", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_chunk_type", table_name="vector_chunks")
    op.drop_table("vector_chunks")

    op.drop_index("ix_news_events_affected_symbols", table_name="news_events")
    op.drop_index("ix_news_events_dedup_hash", table_name="news_events")
    op.drop_index("ix_news_events_severity", table_name="news_events")
    op.drop_index("ix_news_events_direction", table_name="news_events")
    op.drop_index("ix_news_events_event_type", table_name="news_events")
    op.drop_index("ix_news_events_published_at", table_name="news_events")
    op.drop_index("ix_news_events_source", table_name="news_events")
    op.drop_table("news_events")
