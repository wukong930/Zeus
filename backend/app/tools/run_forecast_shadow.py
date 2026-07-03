"""CLI: shadow-track the governed forecast signal.

Default: score any due (horizon-elapsed) forecasts and report the accumulated
shadow performance. --backfill seeds the shadow track by emitting + scoring a
monthly forecast across the whole history (reusing the same reversal_weights /
feature_hash as the live service) so the production pipeline's track record can
be compared to the validated backtest. Everything is advisory / shadow.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_forecast_shadow --backfill
    .venv/bin/python -m app.tools.run_forecast_shadow
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.forecast import ForecastRecord
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series
from app.services.prediction.cross_sectional import (
    MODEL_VERSION,
    feature_hash,
    reversal_weights,
)
from app.services.prediction.shadow import (
    MAX_ABS_RETURN,
    score_due_forecasts,
    shadow_performance,
)

WARMUP_DAYS = 120


async def _backfill(session, *, k: int, lookback: int, horizon: int) -> int:
    symbols = sorted(SECTOR_BY_SYMBOL)
    series: dict[str, pd.Series] = {}
    for symbol in symbols:
        bars = await load_main_series(session, symbol)
        if bars:
            series[symbol] = pd.Series({bar.timestamp: bar.close for bar in bars})
    close = pd.DataFrame(series).sort_index()
    logp = np.log(close)
    momentum = logp - logp.shift(lookback)
    forward = close.shift(-horizon) / close - 1.0
    index = close.index
    signal = f"xs_reversal_mom{lookback}"

    existing = set(
        (await session.scalars(select(ForecastRecord.as_of).where(ForecastRecord.signal == signal))).all()
    )
    now = datetime.now(timezone.utc)
    rows: list[ForecastRecord] = []
    for position in range(WARMUP_DAYS, len(index) - horizon, horizon):
        day = index[position]
        if day.to_pydatetime() in existing:
            continue
        mom_row = {
            symbol: (None if pd.isna(value) else float(value))
            for symbol, value in momentum.loc[day].items()
        }
        weights = reversal_weights(mom_row, k=k)
        if not weights:
            continue
        realized = 0.0
        priced = True
        for symbol, weight in weights.items():
            value = forward.loc[day, symbol]
            if pd.isna(value):
                priced = False
                break
            clipped = 0.0 if abs(float(value)) > MAX_ABS_RETURN else float(value)
            realized += weight * clipped
        if not priced:
            continue
        rows.append(
            ForecastRecord(
                as_of=day.to_pydatetime(),
                signal=signal,
                model_version=MODEL_VERSION,
                feature_hash=feature_hash(day.to_pydatetime(), signal, mom_row),
                target_weights=weights,
                universe_size=sum(1 for v in mom_row.values() if v is not None),
                decision_grade=False,
                horizon_days=horizon,
                realized_return=realized,
                resolved_at=now,
            )
        )
    session.add_all(rows)
    await session.commit()
    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow-track the governed forecast signal")
    parser.add_argument("--backfill", action="store_true", help="seed monthly forecasts over history")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--lookback", type=int, default=120)
    parser.add_argument("--horizon", type=int, default=21)
    args = parser.parse_args()

    signal = f"xs_reversal_mom{args.lookback}"
    async with AsyncSessionLocal() as session:
        if args.backfill:
            seeded = await _backfill(session, k=args.k, lookback=args.lookback, horizon=args.horizon)
            print(f"backfill: seeded {seeded} resolved shadow forecasts for {signal}")
        else:
            scored = await score_due_forecasts(session, now=datetime.now(timezone.utc), signal=signal)
            await session.commit()
            print(f"scored: scanned {scored.scanned}, resolved {scored.resolved}, pending {scored.pending}")

        perf = await shadow_performance(session, signal=signal)

    print(f"\n=== shadow performance: {signal} (advisory / non-authoritative) ===")
    if perf.resolved == 0:
        print("no resolved forecasts yet")
        return
    ann = perf.mean_return * 12 * 100
    print(
        f"resolved {perf.resolved}  mean/period {perf.mean_return * 100:+.3f}%  ann {ann:+.2f}%  "
        f"win {perf.win_rate * 100:.1f}%"
    )
    if perf.deflated is not None:
        d = perf.deflated
        verdict = "SIGNIFICANT" if d.passed_gate else "not significant"
        print(f"sharpe {perf.sharpe:+.2f}  |  deflated {d.deflated_sharpe:+.2f} (p={d.deflated_pvalue:.3f})  -> {verdict}")
    print("\nshadow track reproduces the production pipeline (emit ForecastRecord -> score realized).")


if __name__ == "__main__":
    asyncio.run(main())
