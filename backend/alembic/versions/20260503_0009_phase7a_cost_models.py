"""phase7a cost model foundations

Revision ID: 20260503_0009
Revises: 20260503_0008
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0009"
down_revision: str | None = "20260503_0008"
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
        "commodity_config",
        _uuid_pk(),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sector", sa.String(length=30), nullable=False),
        sa.Column("cost_formula", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cost_chain", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_sources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("uncertainty_pct", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", name="uq_commodity_config_symbol"),
    )
    op.create_index("ix_commodity_config_sector", "commodity_config", ["sector"])
    op.create_index("ix_commodity_config_enabled", "commodity_config", ["enabled"])

    op.create_table(
        "cost_snapshots",
        _uuid_pk(),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sector", sa.String(length=30), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("current_price", sa.Float()),
        sa.Column("total_unit_cost", sa.Float(), nullable=False),
        sa.Column("breakeven_p25", sa.Float(), nullable=False),
        sa.Column("breakeven_p50", sa.Float(), nullable=False),
        sa.Column("breakeven_p75", sa.Float(), nullable=False),
        sa.Column("breakeven_p90", sa.Float(), nullable=False),
        sa.Column("profit_margin", sa.Float()),
        sa.Column("cost_breakdown", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("inputs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_sources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("uncertainty_pct", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("formula_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "snapshot_date", name="uq_cost_snapshots_symbol_date"),
    )
    op.create_index("ix_cost_snapshots_symbol", "cost_snapshots", ["symbol"])
    op.create_index("ix_cost_snapshots_sector", "cost_snapshots", ["sector"])
    op.create_index("ix_cost_snapshots_snapshot_date", "cost_snapshots", ["snapshot_date"])

    commodity_config = sa.table(
        "commodity_config",
        sa.column("symbol", sa.String),
        sa.column("name", sa.Text),
        sa.column("sector", sa.String),
        sa.column("cost_formula", postgresql.JSONB),
        sa.column("cost_chain", postgresql.JSONB),
        sa.column("parameters", postgresql.JSONB),
        sa.column("data_sources", postgresql.JSONB),
        sa.column("uncertainty_pct", sa.Float),
    )
    op.bulk_insert(
        commodity_config,
        [
            _config_row("JM", "Coking Coal", "coking_coal", []),
            _config_row("J", "Coke", "coke", ["JM"]),
            _config_row("I", "Iron Ore", "iron_ore", []),
            _config_row("RB", "Rebar", "rebar", ["I", "J"]),
            _config_row("HC", "Hot Coil", "hot_coil", ["I", "J", "RB"]),
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_snapshots_snapshot_date", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_sector", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_symbol", table_name="cost_snapshots")
    op.drop_table("cost_snapshots")
    op.drop_index("ix_commodity_config_enabled", table_name="commodity_config")
    op.drop_index("ix_commodity_config_sector", table_name="commodity_config")
    op.drop_table("commodity_config")


def _config_row(symbol: str, name: str, formula: str, upstream: list[str]) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "sector": "ferrous",
        "cost_formula": {"name": formula, "version": "phase7a.v1"},
        "cost_chain": upstream,
        "parameters": {"public_fallback": True},
        "data_sources": [
            {
                "name": "public fallback",
                "type": "manual_seed",
                "quality": "rough",
                "note": "Phase 7a bootstrap; replace with exchange/industry data as connectors mature.",
            }
        ],
        "uncertainty_pct": 0.05,
    }
