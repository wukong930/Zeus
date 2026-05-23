"""add llm config query index

Revision ID: 20260524_0035
Revises: 20260524_0034
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0035"
down_revision: str | None = "20260524_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_llm_config_enabled_updated_id",
        "llm_config",
        ["enabled", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_config_enabled_updated_id", table_name="llm_config")
