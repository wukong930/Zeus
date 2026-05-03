"""phase85 backtest correctness guards

Revision ID: 20260503_0011
Revises: 20260503_0010
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0011"
down_revision: str | None = "20260503_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "strategy_runs",
        _uuid_pk(),
        sa.Column("strategy_hash", sa.String(length=80), nullable=False),
        sa.Column("strategy_name", sa.Text()),
        sa.Column("strategy_space", sa.String(length=80), nullable=False, server_default="default"),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_sharpe", sa.Float(), nullable=False),
        sa.Column("deflated_sharpe", sa.Float(), nullable=False),
        sa.Column("deflated_pvalue", sa.Float(), nullable=False),
        sa.Column("fdr_method", sa.String(length=30)),
        sa.Column("fdr_threshold", sa.Float()),
        sa.Column("passed_gate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("calibration_strategy", sa.String(length=20), nullable=False, server_default="pit"),
        sa.Column("result_warning", sa.Text()),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("run_by", sa.String(length=80)),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_strategy_runs_hash", "strategy_runs", ["strategy_hash"])
    op.create_index("ix_strategy_runs_space", "strategy_runs", ["strategy_space"])
    op.create_index("ix_strategy_runs_run_at", "strategy_runs", ["run_at"])
    op.create_index(
        "ix_strategy_runs_calibration_strategy",
        "strategy_runs",
        ["calibration_strategy"],
    )

    op.create_table(
        "slippage_models",
        _uuid_pk(),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("contract_tier", sa.String(length=20), nullable=False),
        sa.Column("base_slippage_bps", sa.Float(), nullable=False),
        sa.Column("vol_multiplier", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "liquidity_multiplier",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("tod_multiplier", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("delivery_multiplier", sa.Float(), nullable=False, server_default="3"),
        sa.Column("limit_locked_fillable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.Text()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_slippage_models_symbol_tier", "slippage_models", ["symbol", "contract_tier"])
    op.create_index("ix_slippage_models_effective", "slippage_models", ["effective_from", "effective_to"])

    op.create_table(
        "live_divergence_metrics",
        _uuid_pk(),
        sa.Column("strategy_hash", sa.String(length=80), nullable=False),
        sa.Column("metric_type", sa.String(length=40), nullable=False),
        sa.Column("backtest_value", sa.Float()),
        sa.Column("live_value", sa.Float()),
        sa.Column("tracking_error", sa.Float()),
        sa.Column("threshold", sa.Float()),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason", sa.Text()),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_live_divergence_strategy", "live_divergence_metrics", ["strategy_hash"])
    op.create_index("ix_live_divergence_type", "live_divergence_metrics", ["metric_type"])
    op.create_index("ix_live_divergence_severity", "live_divergence_metrics", ["severity"])
    op.create_index("ix_live_divergence_computed_at", "live_divergence_metrics", ["computed_at"])

    op.create_table(
        "commodity_history",
        _uuid_pk(),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.String(length=20)),
        sa.Column("name", sa.Text()),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column("active_to", sa.Date()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_commodity_history_symbol", "commodity_history", ["symbol"])
    op.create_index("ix_commodity_history_active", "commodity_history", ["active_from", "active_to"])


def downgrade() -> None:
    op.drop_index("ix_commodity_history_active", table_name="commodity_history")
    op.drop_index("ix_commodity_history_symbol", table_name="commodity_history")
    op.drop_table("commodity_history")

    op.drop_index("ix_live_divergence_computed_at", table_name="live_divergence_metrics")
    op.drop_index("ix_live_divergence_severity", table_name="live_divergence_metrics")
    op.drop_index("ix_live_divergence_type", table_name="live_divergence_metrics")
    op.drop_index("ix_live_divergence_strategy", table_name="live_divergence_metrics")
    op.drop_table("live_divergence_metrics")

    op.drop_index("ix_slippage_models_effective", table_name="slippage_models")
    op.drop_index("ix_slippage_models_symbol_tier", table_name="slippage_models")
    op.drop_table("slippage_models")

    op.drop_index("ix_strategy_runs_calibration_strategy", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_run_at", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_space", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_hash", table_name="strategy_runs")
    op.drop_table("strategy_runs")
