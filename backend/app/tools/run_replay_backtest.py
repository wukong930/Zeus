"""CLI: replay price signals over the backfilled history and backtest them.

Turns the deep daily history (see backfill_akshare_history) into a large,
multi-regime sample by replaying the deterministic price evaluators, then feeds
the result to the A-1 cost-aware backtest. This is the first credible read on
whether the price-based directional signals have an edge.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_replay_backtest
    .venv/bin/python -m app.tools.run_replay_backtest --symbols RB,CU,I --cost-bps 6
    .venv/bin/python -m app.tools.run_replay_backtest --horizon 20
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import AsyncSessionLocal
from app.services.backtest.replay import SECTOR_BY_SYMBOL, replay_price_signals
from app.services.backtest.signal_backtest import run_signal_backtest
from app.tools.run_signal_backtest import HORIZONS, _format_report


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay price signals over history and backtest")
    parser.add_argument("--symbols", default=None, help="comma-separated; default = built-in set")
    parser.add_argument(
        "--horizon", type=int, choices=HORIZONS, default=None, help="single horizon; default 1/5/20"
    )
    parser.add_argument("--cost-bps", type=float, default=None, help="round-trip cost override (bps)")
    parser.add_argument("--lookback", type=int, default=60, help="bars of context per evaluation")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(SECTOR_BY_SYMBOL)

    print(f"replaying {len(symbols)} symbols over backfilled history ...")
    async with AsyncSessionLocal() as session:
        signals = await replay_price_signals(session, symbols=symbols, lookback=args.lookback)

    by_type: dict[str, int] = {}
    for signal in signals:
        by_type[signal.signal_type] = by_type.get(signal.signal_type, 0) + 1
    days = sorted({signal.created_at.date() for signal in signals if signal.created_at})
    print(f"replayed signals: {len(signals)}  by type: {by_type}")
    if days:
        print(f"signal span: {days[0]} → {days[-1]}  ({len(days)} distinct days)")

    horizons = (args.horizon,) if args.horizon else HORIZONS
    for horizon in horizons:
        report = run_signal_backtest(signals, horizon=horizon, round_trip_cost_bps=args.cost_bps)
        print(_format_report(report))
    print(
        "\nnote: replayed price signals only (momentum/price_gap). A real edge must clear the "
        "Deflated Sharpe gate, not just >50%."
    )


if __name__ == "__main__":
    asyncio.run(main())
