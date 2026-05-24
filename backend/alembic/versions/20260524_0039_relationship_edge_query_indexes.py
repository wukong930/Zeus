"""add relationship edge query indexes

Revision ID: 20260524_0039
Revises: 20260524_0038
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0039"
down_revision: str | None = "20260524_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_relationship_edges_source_strength_id",
        "relationship_edges",
        ["source", "strength", "id"],
    )
    op.create_index(
        "ix_relationship_edges_target_strength_id",
        "relationship_edges",
        ["target", "strength", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_relationship_edges_target_strength_id", table_name="relationship_edges")
    op.drop_index("ix_relationship_edges_source_strength_id", table_name="relationship_edges")
