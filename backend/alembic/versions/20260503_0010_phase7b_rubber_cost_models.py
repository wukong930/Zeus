"""phase7b rubber cost model configs

Revision ID: 20260503_0010
Revises: 20260503_0009
Create Date: 2026-05-03
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa

revision: str = "20260503_0010"
down_revision: str | None = "20260503_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    data_sources = [
        {
            "name": "public rubber fallback",
            "type": "manual_seed",
            "quality": "rough",
            "note": "Phase 7b bootstrap using Qingdao/Hainan/Yunnan/Thailand/freight proxies.",
        }
    ]
    statement = sa.text(
        """
            INSERT INTO commodity_config (
                symbol, name, sector, cost_formula, cost_chain, parameters, data_sources,
                uncertainty_pct
            )
            VALUES (
                :symbol,
                :name,
                'rubber',
                CAST(:cost_formula AS jsonb),
                CAST(:cost_chain AS jsonb),
                CAST(:parameters AS jsonb),
                CAST(:data_sources AS jsonb),
                0.07
            )
            ON CONFLICT (symbol) DO NOTHING
        """
    )
    for row in (
        {
            "symbol": "NR",
            "name": "Natural Rubber",
            "cost_formula": {"name": "natural_rubber", "version": "phase7b.v1"},
            "cost_chain": [],
        },
        {
            "symbol": "RU",
            "name": "SHFE Rubber",
            "cost_formula": {"name": "rubber_processed", "version": "phase7b.v1"},
            "cost_chain": ["NR"],
        },
    ):
        bind.execute(
            statement,
            {
                **row,
                "cost_formula": json.dumps(row["cost_formula"]),
                "cost_chain": json.dumps(row["cost_chain"]),
                "parameters": json.dumps({"public_fallback": True, "seasonality_enabled": True}),
                "data_sources": json.dumps(data_sources),
            },
        )


def downgrade() -> None:
    op.execute("DELETE FROM commodity_config WHERE symbol IN ('NR', 'RU')")
