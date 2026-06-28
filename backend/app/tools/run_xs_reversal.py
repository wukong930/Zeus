"""CLI: cross-sectional reversal long-short portfolio backtest.

Turns the cross-sectional reversal IC into a tradable P&L: each rebalance, rank
the universe by a signal and go LONG the bottom-k (losers) / SHORT the top-k
(winners), dollar-neutral, hold to the next rebalance, net of turnover cost.
Reports Sharpe / Deflated Sharpe per signal over the 16-year history.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_xs_reversal
    .venv/bin/python -m app.tools.run_xs_reversal --k 4 --cost-bps 8 --hold 21
"""

from __future__ import annotations

import argparse
import asyncio

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series
from app.services.backtest.xs_reversal import (
    gross_period_return,
    one_way_turnover,
    run_xs_backtest,
    select_long_short,
)

WARMUP_DAYS = 120
TRADING_DAYS_PER_YEAR = 252


def _signal_frames(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logp = np.log(close)
    return {
        "mom_20": logp - logp.shift(20),
        "mom_60": logp - logp.shift(60),
        "mom_120": logp - logp.shift(120),
        "dist_ma60": (close - close.rolling(60).mean()) / close.rolling(60).mean(),
    }


def _row(frame: pd.DataFrame, day) -> dict[str, float | None]:
    return {
        symbol: (None if pd.isna(value) else float(value))
        for symbol, value in frame.loc[day].items()
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-sectional reversal long-short backtest")
    parser.add_argument("--k", type=int, default=5, help="symbols per leg")
    parser.add_argument("--cost-bps", type=float, default=5.0, help="round-trip cost per position")
    parser.add_argument("--hold", type=int, default=21, help="rebalance / holding period in days")
    args = parser.parse_args()

    symbols = sorted(SECTOR_BY_SYMBOL)
    print(f"loading {len(symbols)} symbols ...")
    series: dict[str, pd.Series] = {}
    async with AsyncSessionLocal() as session:
        for symbol in symbols:
            bars = await load_main_series(session, symbol)
            if bars:
                series[symbol] = pd.Series({bar.timestamp: bar.close for bar in bars})

    close = pd.DataFrame(series).sort_index()
    print(f"panel: {close.shape[1]} symbols x {close.shape[0]} days")

    signals = _signal_frames(close)
    forward = close.shift(-args.hold) / close - 1.0  # holding-period simple return
    index = close.index
    rebalance = list(range(WARMUP_DAYS, len(index) - args.hold, args.hold))
    periods_per_year = round(TRADING_DAYS_PER_YEAR / args.hold)
    trials = len(signals)

    print(
        f"\nrebalances: {len(rebalance)} (every {args.hold}d), k={args.k}/leg, "
        f"cost {args.cost_bps}bps/position\n"
    )
    header = (
        f"{'signal':<11}{'periods':>8}{'gross/p':>9}{'net/p':>8}{'ann.net':>9}"
        f"{'win':>7}{'sharpe':>8}{'deflated':>10}{'turn':>7}   verdict"
    )
    print(header)
    for name, frame in signals.items():
        gross: list[float] = []
        turnovers: list[float] = []
        previous: set[str] = set()
        for position in rebalance:
            day = index[position]
            long, short = select_long_short(_row(frame, day), k=args.k)
            if not long:
                continue
            period_return = gross_period_return(long, short, _row(forward, day))
            if period_return is None:
                continue
            current = set(long) | set(short)
            turnovers.append(one_way_turnover(previous, current))
            gross.append(period_return)
            previous = current

        report = run_xs_backtest(
            name,
            gross,
            turnovers,
            quantile_k=args.k,
            cost_bps=args.cost_bps,
            periods_per_year=periods_per_year,
            trials=trials,
        )
        if not report.periods or report.deflated is None:
            print(f"{name:<11}{report.periods:>8}   (insufficient periods)")
            continue
        d = report.deflated
        ann = report.net_mean_return * periods_per_year
        verdict = "SIGNIFICANT" if report.has_significant_edge else "no edge"
        print(
            f"{name:<11}{report.periods:>8}{report.gross_mean_return * 100:>+8.3f}%"
            f"{report.net_mean_return * 100:>+7.3f}%{ann * 100:>+8.2f}%"
            f"{report.win_rate * 100:>6.1f}%{report.sharpe:>+8.2f}"
            f"{d.deflated_sharpe:>+9.2f}{report.avg_turnover * 100:>6.0f}%   {verdict}"
        )
    print(
        "\nLong losers / short winners (cross-sectional reversal), dollar-neutral, monthly. "
        "sharpe/deflated are annualized; a real strategy clears the Deflated Sharpe gate net of cost."
    )


if __name__ == "__main__":
    asyncio.run(main())
