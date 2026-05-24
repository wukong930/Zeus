"""add contract metadata lookup index

Revision ID: 20260524_0042
Revises: 20260524_0041
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0042"
down_revision: str | None = "20260524_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_contract_metadata_current_lookup",
        "contract_metadata",
        ["symbol", "is_main", "main_until", "main_from", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contract_metadata_current_lookup", table_name="contract_metadata")
