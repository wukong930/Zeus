"""add forecast_records (governed cross-sectional forecast)

Revision ID: 20260628_0001
Revises: 20260529_0052
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260628_0001"
down_revision: str | None = "20260529_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal", sa.String(length=60), nullable=False),
        sa.Column("model_version", sa.String(length=60), nullable=False),
        sa.Column("feature_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "target_weights",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "decision_grade",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_forecast_records_signal", "forecast_records", ["signal"])
    op.create_index("ix_forecast_records_as_of", "forecast_records", ["as_of"])
    op.create_index(
        "ix_forecast_records_signal_as_of_id",
        "forecast_records",
        ["signal", "as_of", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_records_signal_as_of_id", table_name="forecast_records")
    op.drop_index("ix_forecast_records_as_of", table_name="forecast_records")
    op.drop_index("ix_forecast_records_signal", table_name="forecast_records")
    op.drop_table("forecast_records")
