"""CLI: multi-factor composite long-short backtest vs the single factors.

Backtests each validated factor (mom_120 reversal, dist_ma60 value, vol_20
low-vol) and their equal-weight cross-sectional z-score composite, long the
bottom-k by signal / short the top-k, to see whether combining lifts the
Deflated Sharpe over the best single factor.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_multi_factor
    .venv/bin/python -m app.tools.run_multi_factor --k 10
"""

from __future__ import annotations

import argparse
import asyncio

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.backtest.multi_factor import composite_score
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series
from app.services.backtest.walk_forward_xs import sub_period_breakdown
from app.services.backtest.xs_reversal import (
    gross_period_return,
    one_way_turnover,
    run_xs_backtest,
    select_long_short,
)

WARMUP_DAYS = 130
TRADING_DAYS_PER_YEAR = 252
FACTORS = ("mom_120", "dist_ma60", "vol_20")


def _factor_frames(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logp = np.log(close)
    ret = close.pct_change()
    return {
        "mom_120": logp - logp.shift(120),
        "dist_ma60": (close - close.rolling(60).mean()) / close.rolling(60).mean(),
        "vol_20": ret.rolling(20).std(),
    }


def _row(frame: pd.DataFrame, day) -> dict[str, float | None]:
    return {s: (None if pd.isna(v) else float(v)) for s, v in frame.loc[day].items()}


def _backtest(signal_at, forward, rebalance, index, *, k, cost_bps):
    gross: list[float] = []
    turnovers: list[float] = []
    dated: list[tuple] = []
    previous: set[str] = set()
    round_trip = cost_bps / 10_000.0
    for position in rebalance:
        day = index[position]
        long, short = select_long_short(signal_at(day), k=k)
        if not long:
            continue
        period = gross_period_return(long, short, _row(forward, day))
        if period is None:
            continue
        current = set(long) | set(short)
        turn = one_way_turnover(previous, current)
        turnovers.append(turn)
        gross.append(period)
        dated.append((day.to_pydatetime(), period - turn * round_trip))
        previous = current
    return gross, turnovers, dated


async def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-factor composite backtest")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--hold", type=int, default=21)
    args = parser.parse_args()

    symbols = sorted(SECTOR_BY_SYMBOL)
    series: dict[str, pd.Series] = {}
    async with AsyncSessionLocal() as session:
        for symbol in symbols:
            bars = await load_main_series(session, symbol)
            if bars:
                series[symbol] = pd.Series({bar.timestamp: bar.close for bar in bars})

    close = pd.DataFrame(series).sort_index()
    print(f"panel: {close.shape[1]} symbols x {close.shape[0]} days")
    frames = _factor_frames(close)
    forward = close.shift(-args.hold) / close - 1.0
    index = close.index
    rebalance = list(range(WARMUP_DAYS, len(index) - args.hold, args.hold))
    ppy = round(TRADING_DAYS_PER_YEAR / args.hold)
    trials = len(FACTORS) + 1

    def composite_at(day):
        return composite_score({factor: _row(frames[factor], day) for factor in FACTORS})

    signals = {factor: (lambda day, f=factor: _row(frames[f], day)) for factor in FACTORS}
    signals["composite"] = composite_at

    print(f"\n{'signal':<12}{'periods':>8}{'net/p':>9}{'ann':>9}{'win':>7}{'sharpe':>8}{'deflated':>10}  verdict")
    composite_dated = None
    for name, signal_at in signals.items():
        gross, turnovers, dated = _backtest(
            signal_at, forward, rebalance, index, k=args.k, cost_bps=args.cost_bps
        )
        report = run_xs_backtest(
            name, gross, turnovers, quantile_k=args.k, cost_bps=args.cost_bps,
            periods_per_year=ppy, trials=trials,
        )
        if name == "composite":
            composite_dated = dated
        if not report.periods or report.deflated is None:
            print(f"{name:<12}{report.periods:>8}  (insufficient)")
            continue
        d = report.deflated
        verdict = "SIGNIFICANT" if report.has_significant_edge else "no edge"
        print(
            f"{name:<12}{report.periods:>8}{report.net_mean_return * 100:>+8.3f}%"
            f"{report.net_mean_return * ppy * 100:>+8.2f}%{report.win_rate * 100:>6.1f}%"
            f"{report.sharpe:>+8.2f}{d.deflated_sharpe:>+9.2f}   {verdict}"
        )

    if composite_dated:
        print("\n=== composite sub-period stability ===")
        for block in sub_period_breakdown(composite_dated, n_blocks=4, periods_per_year=ppy):
            print(
                f"  {block.label:<26}{block.periods:>4}  mean/p {block.mean_return * 100:+.3f}%"
                f"  win {block.win_rate * 100:.1f}%  sharpe {block.sharpe:+.2f}"
            )
    print("\nequal-weight cross-sectional z-score composite of reversal + value + low-vol.")


if __name__ == "__main__":
    asyncio.run(main())
