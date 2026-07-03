"""add vector evaluation query indexes

Revision ID: 20260503_0024
Revises: 20260503_0023
Create Date: 2026-05-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0024"
down_revision: str | None = "20260503_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_vector_eval_set_status_created_at_id",
        "vector_eval_set",
        ["status", "created_at", "id"],
    )
    op.create_index(
        "ix_vector_chunks_quality_created_at_id",
        "vector_chunks",
        ["quality_status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vector_chunks_quality_created_at_id", table_name="vector_chunks")
    op.drop_index("ix_vector_eval_set_status_created_at_id", table_name="vector_eval_set")
