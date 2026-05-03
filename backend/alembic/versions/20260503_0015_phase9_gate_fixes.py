"""phase9 gate hardening fixes

Revision ID: 20260503_0015
Revises: 20260503_0014
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260503_0015"
down_revision: str | None = "20260503_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_event_log_event_channel_status",
        "event_log",
        ["event_id", "channel", "status"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_event_log_event_channel_status",
        "event_log",
        type_="unique",
    )
