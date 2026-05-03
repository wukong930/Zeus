"""phase6 positions and recommendation attribution

Revision ID: 20260503_0008
Revises: 20260503_0007
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0008"
down_revision: str | None = "20260503_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("manual_entry", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("positions", sa.Column("avg_entry_price", sa.Float()))
    op.add_column(
        "positions",
        sa.Column("monitoring_priority", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column(
        "positions",
        sa.Column(
            "propagation_nodes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "positions",
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("positions", sa.Column("stale_since", sa.DateTime(timezone=True)))
    op.add_column(
        "positions",
        sa.Column("data_mode", sa.String(length=30), nullable=False, server_default="position_aware"),
    )
    op.create_index("ix_positions_recommendation_id", "positions", ["recommendation_id"])
    op.create_index("ix_positions_monitoring_priority", "positions", ["monitoring_priority"])
    op.create_index("ix_positions_data_mode", "positions", ["data_mode"])

    op.add_column("recommendations", sa.Column("entry_price", sa.Float()))
    op.add_column("recommendations", sa.Column("stop_loss", sa.Float()))
    op.add_column("recommendations", sa.Column("take_profit", sa.Float()))
    op.add_column("recommendations", sa.Column("actual_entry", sa.Float()))
    op.add_column("recommendations", sa.Column("actual_exit", sa.Float()))
    op.add_column("recommendations", sa.Column("actual_exit_reason", sa.String(length=40)))
    op.add_column("recommendations", sa.Column("pnl_realized", sa.Float()))
    op.add_column("recommendations", sa.Column("mae", sa.Float()))
    op.add_column("recommendations", sa.Column("mfe", sa.Float()))
    op.add_column("recommendations", sa.Column("holding_period_days", sa.Float()))
    op.create_index(
        "ix_recommendations_actual_exit_reason",
        "recommendations",
        ["actual_exit_reason"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_actual_exit_reason", table_name="recommendations")
    op.drop_column("recommendations", "holding_period_days")
    op.drop_column("recommendations", "mfe")
    op.drop_column("recommendations", "mae")
    op.drop_column("recommendations", "pnl_realized")
    op.drop_column("recommendations", "actual_exit_reason")
    op.drop_column("recommendations", "actual_exit")
    op.drop_column("recommendations", "actual_entry")
    op.drop_column("recommendations", "take_profit")
    op.drop_column("recommendations", "stop_loss")
    op.drop_column("recommendations", "entry_price")

    op.drop_index("ix_positions_data_mode", table_name="positions")
    op.drop_index("ix_positions_monitoring_priority", table_name="positions")
    op.drop_index("ix_positions_recommendation_id", table_name="positions")
    op.drop_column("positions", "data_mode")
    op.drop_column("positions", "stale_since")
    op.drop_column("positions", "last_updated_at")
    op.drop_column("positions", "propagation_nodes")
    op.drop_column("positions", "monitoring_priority")
    op.drop_column("positions", "avg_entry_price")
    op.drop_column("positions", "manual_entry")
