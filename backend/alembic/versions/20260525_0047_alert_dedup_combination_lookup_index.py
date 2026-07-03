"""add alert dedup combination lookup index

Revision ID: 20260525_0047
Revises: 20260525_0046
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260525_0047"
down_revision: str | None = "20260525_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_alert_dedup_combination_lookup",
        "alert_dedup_cache",
        ["signal_combination_hash", "symbol", "direction", "last_emitted_at", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_dedup_combination_lookup", table_name="alert_dedup_cache")
