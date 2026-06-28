"""CLI: cross-sectional information-coefficient probe over the price history.

Measures whether any continuous feature predicts the cross-section of forward
returns — the cheap, high-information gate for whether a full ML prediction head
(Track B) is worth building. Reports mean IC, t-stat and %-positive per feature
and horizon over the backfilled 16-year panel.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_ic_probe
"""

from __future__ import annotations

import argparse
import asyncio

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.backtest.cross_sectional_ic import aggregate_ic
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series

HORIZONS = (5, 20, 60)
MAX_ABS_FWD = 0.5  # drop contract-roll artifacts before ranking


def _feature_frames(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logp = np.log(close)
    ret = close.pct_change()
    return {
        "mom_20": logp - logp.shift(20),
        "mom_60": logp - logp.shift(60),
        "mom_120": logp - logp.shift(120),
        "rev_5": logp - logp.shift(5),
        "vol_20": ret.rolling(20).std(),
        "dist_ma60": (close - close.rolling(60).mean()) / close.rolling(60).mean(),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-sectional IC probe over price history")
    parser.add_argument("--symbols", default=None, help="comma-separated; default = built-in set")
    args = parser.parse_args()

    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else sorted(SECTOR_BY_SYMBOL)
    )

    print(f"loading {len(symbols)} symbols ...")
    series: dict[str, pd.Series] = {}
    async with AsyncSessionLocal() as session:
        for symbol in symbols:
            bars = await load_main_series(session, symbol)
            if bars:
                series[symbol] = pd.Series({bar.timestamp: bar.close for bar in bars})

    close = pd.DataFrame(series).sort_index()
    print(
        f"panel: {close.shape[1]} symbols x {close.shape[0]} days "
        f"({close.index.min().date()} -> {close.index.max().date()})"
    )

    features = _feature_frames(close)
    logp = np.log(close)

    print(f"\n{'feature':<12}{'h':>4}{'mean_IC':>10}{'t_stat':>9}{'%pos':>7}   sig")
    for horizon in HORIZONS:
        forward = logp.shift(-horizon) - logp
        forward = forward.where(forward.abs() <= MAX_ABS_FWD)
        for name, frame in features.items():
            daily = frame.corrwith(forward, axis=1, method="spearman").dropna()
            result = aggregate_ic(name, horizon, [float(value) for value in daily.to_numpy()])
            flag = "  <== significant" if result.is_significant else ""
            print(
                f"{name:<12}{horizon:>4}{result.mean_ic:>+10.4f}{result.t_stat:>+9.2f}"
                f"{result.pct_positive * 100:>6.1f}%{flag}"
            )
    print(
        "\nIC = daily cross-sectional Spearman(feature, forward return), robust to roll-magnitude "
        "artifacts. |t|>3 with |IC|>=0.01 over thousands of days => a real factor worth modeling."
    )


if __name__ == "__main__":
    asyncio.run(main())
