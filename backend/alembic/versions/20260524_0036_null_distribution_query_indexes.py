"""add null distribution query indexes

Revision ID: 20260524_0036
Revises: 20260524_0035
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0036"
down_revision: str | None = "20260524_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_null_distribution_lookup_stable",
        "null_distribution_cache",
        ["signal_type", "category", "computed_for", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_null_distribution_lookup_stable",
        table_name="null_distribution_cache",
    )
