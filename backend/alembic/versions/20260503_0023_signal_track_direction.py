"""persist signal direction for event intelligence ingress

Revision ID: 20260503_0023
Revises: 20260503_0022
Create Date: 2026-05-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260503_0023"
down_revision: str | None = "20260503_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signal_track", sa.Column("direction", sa.String(length=20), nullable=True))
    op.create_index("ix_signal_track_direction", "signal_track", ["direction"])


def downgrade() -> None:
    op.drop_index("ix_signal_track_direction", table_name="signal_track")
    op.drop_column("signal_track", "direction")
