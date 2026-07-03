"""CLI: walk-forward / out-of-sample validation of the XS reversal strategy.

Computes the per-signal monthly net returns, then reports (1) the best fixed
signal's performance broken down by calendar sub-period (consistency), and (2) a
rolling walk-forward where the signal is selected on the trailing train window
and applied to the next unseen test window — a genuine out-of-sample track.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_walk_forward
    .venv/bin/python -m app.tools.run_walk_forward --k 5 --train 60 --test 12
"""

from __future__ import annotations

import argparse
import asyncio

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series
from app.services.backtest.walk_forward_xs import sub_period_breakdown, walk_forward_oos
from app.services.backtest.xs_reversal import (
    gross_period_return,
    one_way_turnover,
    select_long_short,
)

WARMUP_DAYS = 120
TRADING_DAYS_PER_YEAR = 252
PRIMARY_SIGNAL = "mom_120"


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


def _dated_net_returns(frame, forward, rebalance, index, *, k, cost_bps):
    round_trip = cost_bps / 10_000.0
    out: list[tuple] = []
    previous: set[str] = set()
    for position in rebalance:
        day = index[position]
        long, short = select_long_short(_row(frame, day), k=k)
        if not long:
            continue
        gross = gross_period_return(long, short, _row(forward, day))
        if gross is None:
            continue
        current = set(long) | set(short)
        turnover = one_way_turnover(previous, current)
        out.append((day.to_pydatetime(), gross - turnover * round_trip))
        previous = current
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward validation of XS reversal")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--hold", type=int, default=21)
    parser.add_argument("--train", type=int, default=60, help="train periods (rebalances)")
    parser.add_argument("--test", type=int, default=12, help="test periods per window")
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
    forward = close.shift(-args.hold) / close - 1.0
    index = close.index
    rebalance = list(range(WARMUP_DAYS, len(index) - args.hold, args.hold))
    periods_per_year = round(TRADING_DAYS_PER_YEAR / args.hold)

    frames = _signal_frames(close)
    returns_by_signal = {
        name: _dated_net_returns(frame, forward, rebalance, index, k=args.k, cost_bps=args.cost_bps)
        for name, frame in frames.items()
    }

    print(f"\n=== sub-period stability of {PRIMARY_SIGNAL} (k={args.k}) ===")
    print(f"{'window':<26}{'periods':>8}{'mean/p':>9}{'win':>7}{'sharpe':>8}")
    for block in sub_period_breakdown(
        returns_by_signal[PRIMARY_SIGNAL], n_blocks=4, periods_per_year=periods_per_year
    ):
        print(
            f"{block.label:<26}{block.periods:>8}{block.mean_return * 100:>+8.3f}%"
            f"{block.win_rate * 100:>6.1f}%{block.sharpe:>+8.2f}"
        )

    print(f"\n=== walk-forward OOS (train {args.train}p, test {args.test}p, select among 4 signals) ===")
    result = walk_forward_oos(
        returns_by_signal, train=args.train, test=args.test, periods_per_year=periods_per_year
    )
    if result.oos_deflated is not None:
        d = result.oos_deflated
        verdict = "SIGNIFICANT edge" if result.has_significant_edge else "no significant edge"
        print(
            f"OOS periods {result.oos_periods}  mean/p {result.oos_mean_return * 100:+.3f}%  "
            f"ann.net {result.oos_mean_return * periods_per_year * 100:+.2f}%  "
            f"win {result.oos_win_rate * 100:.1f}%"
        )
        print(
            f"OOS sharpe {result.oos_sharpe:+.2f}  |  deflated {d.deflated_sharpe:+.2f} "
            f"(p={d.deflated_pvalue:.3f})  -> {verdict}"
        )
        picks: dict[str, int] = {}
        for _, signal in result.selections:
            picks[signal] = picks.get(signal, 0) + 1
        print(f"signal picked per window: {picks}")
    else:
        print("insufficient OOS periods")
    print(
        "\nOOS track selects the signal using only the trailing window, then trades the next "
        "unseen window. A significant OOS deflated Sharpe means the strategy genuinely generalizes."
    )


if __name__ == "__main__":
    asyncio.run(main())
