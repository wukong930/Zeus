"""phase9 learning hypotheses and vector eval set

Revision ID: 20260503_0014
Revises: 20260503_0013
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0014"
down_revision: str | None = "20260503_0013"
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
        "learning_hypotheses",
        _uuid_pk(),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("supporting_evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("proposed_change", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counterevidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("evidence_strength", sa.String(length=30), nullable=False, server_default="weak_evidence"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("source_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_hypotheses_status", "learning_hypotheses", ["status"])
    op.create_index(
        "ix_learning_hypotheses_evidence_strength",
        "learning_hypotheses",
        ["evidence_strength"],
    )
    op.create_index("ix_learning_hypotheses_created_at", "learning_hypotheses", ["created_at"])

    op.create_table(
        "vector_eval_set",
        _uuid_pk(),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("relevant_chunk_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("reviewed_by", sa.String(length=80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vector_eval_set_status", "vector_eval_set", ["status"])
    op.create_index("ix_vector_eval_set_created_at", "vector_eval_set", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_vector_eval_set_created_at", table_name="vector_eval_set")
    op.drop_index("ix_vector_eval_set_status", table_name="vector_eval_set")
    op.drop_table("vector_eval_set")

    op.drop_index("ix_learning_hypotheses_created_at", table_name="learning_hypotheses")
    op.drop_index("ix_learning_hypotheses_evidence_strength", table_name="learning_hypotheses")
    op.drop_index("ix_learning_hypotheses_status", table_name="learning_hypotheses")
    op.drop_table("learning_hypotheses")
