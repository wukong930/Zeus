"""CLI: term-structure carry factor probe (SHFE per-contract via AKShare).

Carry (roll yield) is the best-documented orthogonal commodity factor, and the
reversal-only signal set lacks it. Tushare `fut_daily` is denied to this token
(code 40203), and AKShare's DCE/CZCE per-contract endpoints are down, but
`get_futures_daily(market="SHFE")` works — so this is a SHFE-only first test.

Everything is computed from ONE source (SHFE per-contract bars): carry from the
two nearest contracts; the reversal reference (mom_120) and forward returns from
a roll-free back-adjusted continuous built off the same bars. We then ask the two
questions that decide whether carry is worth productionizing:
  1. Does carry have a real cross-sectional IC vs forward returns?
  2. Is it orthogonal to the validated mom_120 reversal factor?

Usage (from backend/, no DB needed — fetches AKShare directly):
    .venv/bin/python -m app.tools.run_carry_probe --start-year 2018
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from app.services.backtest.carry import carry_signal
from app.services.backtest.cross_sectional_ic import aggregate_ic
from app.services.backtest.roll_adjust import ContractBar, back_adjusted_closes

# SHFE varieties present in the 49-symbol universe (the cross-section grows over
# time as newer contracts — SS 2019, SP 2018, AO/BR 2023 — start trading).
SHFE_VARIETIES = {
    "RB", "HC", "CU", "AL", "ZN", "NI", "AU", "AG",
    "RU", "BR", "SS", "SN", "PB", "AO", "BU", "FU", "SP",
}
MARKET = "SHFE"
HORIZONS = (20, 60)
MAX_ABS_FWD = 0.5
MIN_OI = 1000.0  # liquidity floor so a stale far contract can't define the slope


def _fetch_contract_bars(start_year: int, end_year: int) -> dict[str, list[ContractBar]]:
    import akshare as ak

    by_variety: dict[str, list[ContractBar]] = defaultdict(list)
    for year in range(start_year, end_year + 1):
        try:
            frame = ak.get_futures_daily(
                start_date=f"{year}0101", end_date=f"{year}1231", market=MARKET
            )
        except Exception as exc:  # noqa: BLE001 - per-year resilience
            print(f"  fetch {MARKET} {year} ERROR: {repr(exc)[:100]}")
            continue
        count = 0
        for row in frame.itertuples(index=False):
            variety = str(getattr(row, "variety", "") or "").upper()
            if variety not in SHFE_VARIETIES:
                continue
            try:
                day = datetime.strptime(str(row.date), "%Y%m%d").date()
                close = float(row.close)
                oi = float(getattr(row, "open_interest", 0) or 0)
            except (ValueError, TypeError):
                continue
            if close > 0:
                by_variety[variety].append(ContractBar(str(row.symbol), day, close, oi))
                count += 1
        print(f"  fetched {MARKET} {year}: {count} relevant contract-bars")
    return by_variety


def _carry_series(bars: list[ContractBar]) -> pd.Series:
    """Daily carry: annualized roll yield of the two nearest liquid contracts."""

    by_day: dict[object, dict[str, tuple[float, float]]] = defaultdict(dict)
    for bar in bars:
        if bar.close > 0:
            by_day[bar.day][bar.contract] = (bar.close, bar.open_interest)
    out: dict[object, float] = {}
    for day, contracts in by_day.items():
        carry = carry_signal(contracts, min_oi=MIN_OI)
        if carry is not None:
            out[pd.Timestamp(day)] = carry
    return pd.Series(out).sort_index()


def _continuous_logp(bars: list[ContractBar]) -> pd.Series:
    """Log of the roll-free back-adjusted dominant-contract continuous series."""

    closes = back_adjusted_closes(bars)
    return pd.Series({pd.Timestamp(day): np.log(level) for day, level in closes}).sort_index()


def main() -> None:
    parser = argparse.ArgumentParser(description="Term-structure carry factor probe (SHFE)")
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    print(f"fetching SHFE per-contract data {args.start_year}-{args.end_year} ...")
    by_variety = _fetch_contract_bars(args.start_year, args.end_year)
    print(f"varieties fetched: {sorted(by_variety)}")

    carry = pd.DataFrame({v: _carry_series(bars) for v, bars in by_variety.items()}).sort_index()
    logp = pd.DataFrame(
        {v: _continuous_logp(bars) for v, bars in by_variety.items()}
    ).sort_index()
    # align carry onto the continuous trading calendar
    carry = carry.reindex(logp.index)
    mom_120 = logp - logp.shift(120)  # reversal reference (negative IC expected)

    print(f"\npanel: {logp.shape[1]} SHFE varieties x {logp.shape[0]} days")
    print(f"carry coverage: {int(carry.notna().sum().sum())} variety-days")
    print(f"\n{'factor':<12}{'h':>4}{'mean_IC':>10}{'t_stat':>9}   sig")
    for horizon in HORIZONS:
        forward = (logp.shift(-horizon) - logp).where(lambda x: x.abs() <= MAX_ABS_FWD)
        for name, frame in (("carry", carry), ("mom_120", mom_120)):
            daily = frame.corrwith(forward, axis=1, method="spearman").dropna()
            result = aggregate_ic(name, horizon, [float(v) for v in daily.to_numpy()])
            flag = "  <== significant" if result.is_significant else ""
            print(
                f"{name:<12}{horizon:>4}{result.mean_ic:>+10.4f}{result.t_stat:>+9.2f}{flag}"
            )

    corr = carry.corrwith(mom_120, axis=1, method="spearman").dropna()
    print("\n=== orthogonality: cross-sectional correlation with mom_120 reversal ===")
    print(f"  carry corr(mom_120) = {corr.mean():+.3f}  (|corr|<0.3 => fairly orthogonal)")
    print(
        "\ncarry is worth combining only if it has a real IC AND is weakly correlated with "
        "reversal. Positive carry-IC + negative mom-IC that are orthogonal would be complementary."
    )


if __name__ == "__main__":
    main()
