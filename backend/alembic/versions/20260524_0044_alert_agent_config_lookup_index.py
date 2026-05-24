"""add alert agent config lookup index

Revision ID: 20260524_0044
Revises: 20260524_0043
Create Date: 2026-05-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260524_0044"
down_revision: str | None = "20260524_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_alert_agent_config_key_updated",
        "alert_agent_config",
        ["key", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_agent_config_key_updated", table_name="alert_agent_config")
