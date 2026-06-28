"""CLI: open-interest factor probe — is OI an orthogonal predictive factor?

The validated reversal family is one correlated cluster; a real Sharpe lift needs
an ORTHOGONAL factor. Open interest is the one extra dimension in our data. This
probes whether OI-change factors have a cross-sectional IC AND a low correlation
with the mom_120 reversal factor — the two conditions for OI to be worth adding.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_oi_probe
"""

from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.backtest.cross_sectional_ic import aggregate_ic
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series

HORIZONS = (20, 60)
MAX_ABS_FWD = 0.5


async def main() -> None:
    symbols = sorted(SECTOR_BY_SYMBOL)
    print(f"loading {len(symbols)} symbols (close + open interest) ...")
    closes: dict[str, pd.Series] = {}
    ois: dict[str, pd.Series] = {}
    async with AsyncSessionLocal() as session:
        for symbol in symbols:
            bars = await load_main_series(session, symbol)
            if not bars:
                continue
            closes[symbol] = pd.Series({bar.timestamp: bar.close for bar in bars})
            ois[symbol] = pd.Series(
                {bar.timestamp: bar.open_interest for bar in bars if bar.open_interest}
            )

    close = pd.DataFrame(closes).sort_index()
    oi = pd.DataFrame(ois).reindex(close.index)
    logp = np.log(close)
    log_oi = np.log(oi.where(oi > 0))

    factors = {
        "mom_120": logp - logp.shift(120),  # reversal reference (negative IC)
        "oi_chg_20": log_oi - log_oi.shift(20),
        "oi_chg_60": log_oi - log_oi.shift(60),
        # price-OI divergence: trailing return signed by whether OI rose with it
        "ret20_x_oichg20": (logp - logp.shift(20)) * np.sign(log_oi - log_oi.shift(20)),
    }

    print(f"\npanel: {close.shape[1]} symbols x {close.shape[0]} days")
    print(f"\n{'factor':<18}{'h':>4}{'mean_IC':>10}{'t_stat':>9}   sig")
    for horizon in HORIZONS:
        forward = (logp.shift(-horizon) - logp).where(lambda x: x.abs() <= MAX_ABS_FWD)
        for name, frame in factors.items():
            daily = frame.corrwith(forward, axis=1, method="spearman").dropna()
            result = aggregate_ic(name, horizon, [float(v) for v in daily.to_numpy()])
            flag = "  <== significant" if result.is_significant else ""
            print(
                f"{name:<18}{horizon:>4}{result.mean_ic:>+10.4f}{result.t_stat:>+9.2f}{flag}"
            )

    print("\n=== orthogonality: cross-sectional correlation with mom_120 reversal ===")
    mom = factors["mom_120"]
    for name in ("oi_chg_20", "oi_chg_60", "ret20_x_oichg20"):
        corr = factors[name].corrwith(mom, axis=1, method="spearman").dropna()
        print(f"  {name:<18} corr(mom_120) = {corr.mean():+.3f}  (|corr|<0.3 => fairly orthogonal)")
    print(
        "\nan OI factor is worth combining only if it has a real IC AND is weakly correlated "
        "with reversal — otherwise it is just more of the same."
    )


if __name__ == "__main__":
    asyncio.run(main())
