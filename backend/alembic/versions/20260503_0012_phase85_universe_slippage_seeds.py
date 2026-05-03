"""phase85 universe and slippage seeds

Revision ID: 20260503_0012
Revises: 20260503_0011
Create Date: 2026-05-04
"""

from collections.abc import Sequence
from datetime import date
import json

from alembic import op
import sqlalchemy as sa

revision: str = "20260503_0012"
down_revision: str | None = "20260503_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYMBOLS: tuple[tuple[str, str, str, date], ...] = (
    ("RB", "SHFE", "Rebar", date(2009, 3, 27)),
    ("HC", "SHFE", "Hot Rolled Coil", date(2014, 3, 21)),
    ("I", "DCE", "Iron Ore", date(2013, 10, 18)),
    ("J", "DCE", "Coke", date(2011, 4, 15)),
    ("JM", "DCE", "Coking Coal", date(2013, 3, 22)),
    ("RU", "SHFE", "Natural Rubber", date(1993, 11, 1)),
    ("NR", "INE", "TSR 20 Rubber", date(2019, 8, 12)),
    ("BR", "SHFE", "Butadiene Rubber", date(2023, 7, 28)),
    ("SC", "INE", "Crude Oil", date(2018, 3, 26)),
    ("FU", "SHFE", "Fuel Oil", date(2004, 8, 25)),
    ("TA", "CZCE", "PTA", date(2006, 12, 18)),
    ("EG", "DCE", "Ethylene Glycol", date(2018, 12, 10)),
    ("CU", "SHFE", "Copper", date(1993, 3, 1)),
    ("AL", "SHFE", "Aluminum", date(1992, 5, 28)),
    ("ZN", "SHFE", "Zinc", date(2007, 3, 26)),
)


def upgrade() -> None:
    bind = op.get_bind()
    history_statement = sa.text(
        """
            INSERT INTO commodity_history (
                symbol, exchange, name, active_from, active_to, status, metadata
            )
            VALUES (
                :symbol, :exchange, :name, :active_from, NULL, 'active',
                CAST(:metadata AS jsonb)
            )
        """
    )
    for symbol, exchange, name, active_from in SYMBOLS:
        bind.execute(
            history_statement,
            {
                "symbol": symbol,
                "exchange": exchange,
                "name": name,
                "active_from": active_from,
                "metadata": json.dumps(
                    {
                        "source": "phase85_bootstrap",
                        "note": "Core Zeus/Causa commodity universe seed; verify exchange records before production-only backtests.",
                    }
                ),
            },
        )

    slippage_statement = sa.text(
        """
            INSERT INTO slippage_models (
                symbol, contract_tier, base_slippage_bps,
                vol_multiplier, liquidity_multiplier, tod_multiplier, source
            )
            VALUES (
                :symbol, :contract_tier, :base_slippage_bps,
                CAST(:vol_multiplier AS jsonb),
                CAST(:liquidity_multiplier AS jsonb),
                CAST(:tod_multiplier AS jsonb),
                'phase85_bootstrap'
            )
        """
    )
    tier_base = {"main": 1.0, "second": 2.5, "third": 8.0}
    payload = {
        "vol_multiplier": json.dumps({"low": 0.7, "medium": 1.0, "high": 1.8}),
        "liquidity_multiplier": json.dumps(
            {"lt_1pct_adv": 1.0, "pct_1_to_5_adv": 1.4, "gte_5pct_adv": 2.5}
        ),
        "tod_multiplier": json.dumps(
            {"main_session": 1.0, "open_15m": 1.5, "close_15m": 1.4, "night": 1.2}
        ),
    }
    for symbol, _, _, _ in SYMBOLS:
        for contract_tier, base_slippage_bps in tier_base.items():
            bind.execute(
                slippage_statement,
                {
                    "symbol": symbol,
                    "contract_tier": contract_tier,
                    "base_slippage_bps": base_slippage_bps,
                    **payload,
                },
            )


def downgrade() -> None:
    symbols = ", ".join(f"'{symbol}'" for symbol, _, _, _ in SYMBOLS)
    op.execute(f"DELETE FROM slippage_models WHERE source = 'phase85_bootstrap' AND symbol IN ({symbols})")
    op.execute(f"DELETE FROM commodity_history WHERE metadata->>'source' = 'phase85_bootstrap' AND symbol IN ({symbols})")
