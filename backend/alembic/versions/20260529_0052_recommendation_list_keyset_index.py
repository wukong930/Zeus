"""add recommendation list keyset pagination index

Revision ID: 20260529_0052
Revises: 20260529_0051
Create Date: 2026-05-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260529_0052"
down_revision: str | None = "20260529_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_recommendations_status_created_id",
        "recommendations",
        ["status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_status_created_id", table_name="recommendations")
