"""CLI: cost-aware cross-sectional CARRY long-short backtest (SHFE).

The IC probe found carry has a strong, mostly-orthogonal cross-sectional IC
(~0.10, t~13). But an IC t-stat is inflated by the autocorrelation of a slow
factor, so it is NOT the honest test. This is: turn carry into a tradable monthly
long-short P&L — each month rank the SHFE universe, go LONG high-carry / SHORT
low-carry, dollar-neutral, hold to the next rebalance, net of turnover cost —
and judge it by Deflated Sharpe + sub-period consistency + a walk-forward where
carry must beat reversal out-of-sample. Same rigor that validated reversal.

For a head-to-head, the reversal signal (-mom_120) and an equal-weight z-score
composite are backtested on the IDENTICAL universe and rebalance calendar.

Per-contract bars are cached to scratchpad on first fetch (~25 min) so re-runs
are instant.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_carry_backtest --start-year 2018
"""

from __future__ import annotations

import argparse
import pickle
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.backtest.roll_adjust import ContractBar
from app.services.backtest.walk_forward_xs import sub_period_breakdown, walk_forward_oos
from app.services.backtest.xs_reversal import (
    gross_period_return,
    one_way_turnover,
    run_xs_backtest,
    select_long_short,
)
from app.tools.run_carry_probe import (
    _carry_series,
    _continuous_logp,
    _fetch_contract_bars,
)

CACHE_DIR = Path(tempfile.gettempdir()) / "zeus_carry_cache"  # per-contract bars; first fetch ~25min
REBAL_K = 5  # long top-5 carry / short bottom-5
COST_BPS = 10.0  # round-trip cost per fully-turned-over name (liquid SHFE)
TRIALS = 12  # Deflated-Sharpe penalty for the factors scanned across this research
PERIODS_PER_YEAR = 12
MAX_ABS_MOM = 1.0


def _load_or_fetch(start_year: int, end_year: int) -> dict[str, list[ContractBar]]:
    cache = CACHE_DIR / f"shfe_contract_bars_{start_year}_{end_year}.pkl"
    if cache.exists():
        print(f"loading cached contract bars from {cache.name}")
        return pickle.loads(cache.read_bytes())
    print(f"fetching SHFE per-contract data {start_year}-{end_year} (will cache) ...")
    by_variety = dict(_fetch_contract_bars(start_year, end_year))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(by_variety))
    print(f"cached {sum(len(v) for v in by_variety.values())} bars -> {cache.name}")
    return by_variety


def _month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of each calendar month present in the index."""

    last: dict[tuple[int, int], pd.Timestamp] = {}
    for ts in index:  # index is sorted, so the final write per key is the month-end
        last[(ts.year, ts.month)] = ts
    return [last[key] for key in sorted(last)]


def _rank_weights(score: dict[str, float | None]) -> dict[str, float]:
    """Dollar-neutral rank weights over the WHOLE cross-section (sum|w|=1).

    Uses every name (not a top/bottom-k cut), so it harvests the full breadth —
    the binding constraint on a 17-name universe. Highest carry gets the largest
    positive weight, lowest the largest negative.
    """

    valid = {s: v for s, v in score.items() if v is not None and np.isfinite(v)}
    n = len(valid)
    if n < 4:
        return {}
    ordered = sorted(valid, key=lambda s: (valid[s], s))
    centered = {s: (rank - (n - 1) / 2) for rank, s in enumerate(ordered)}
    norm = sum(abs(c) for c in centered.values())
    if norm == 0:
        return {}
    return {s: c / norm for s, c in centered.items()}


def _backtest_rank_weighted(
    name: str,
    score_panel: pd.DataFrame,
    logp: pd.DataFrame,
    rebal: list[pd.Timestamp],
) -> tuple[object, list[tuple[datetime, float]]]:
    from app.services.backtest.xs_reversal import MAX_ABS_PERIOD_RETURN

    gross_returns: list[float] = []
    turnovers: list[float] = []
    dated_net: list[tuple[datetime, float]] = []
    prev_w: dict[str, float] = {}
    round_trip = COST_BPS / 10_000.0
    for current, nxt in zip(rebal[:-1], rebal[1:], strict=False):
        score = {s: (float(v) if pd.notna(v) else None) for s, v in score_panel.loc[current].items()}
        weights = _rank_weights(score)
        if not weights:
            continue
        gross = 0.0
        used = 0.0
        for sym, weight in weights.items():
            fwd = logp.loc[nxt, sym] - logp.loc[current, sym]
            if pd.notna(fwd) and abs(float(fwd)) <= MAX_ABS_PERIOD_RETURN:
                gross += weight * float(fwd)
                used += abs(weight)
        if used < 0.5:  # need most of the book priced to trust the period
            continue
        names = set(weights) | set(prev_w)
        turnover = 0.5 * sum(abs(weights.get(s, 0.0) - prev_w.get(s, 0.0)) for s in names)
        prev_w = weights
        gross_returns.append(gross)
        turnovers.append(turnover)
        dated_net.append(
            (
                datetime(nxt.year, nxt.month, nxt.day, tzinfo=timezone.utc),
                gross - turnover * round_trip,
            )
        )
    report = run_xs_backtest(
        name,
        gross_returns,
        turnovers,
        quantile_k=0,
        cost_bps=COST_BPS,
        periods_per_year=PERIODS_PER_YEAR,
        trials=TRIALS,
    )
    return report, dated_net


def _select_top_bottom(score: dict[str, float | None], k: int):
    """Long top-k (highest expected-return score) / short bottom-k."""

    negated = {s: (-v if v is not None and np.isfinite(v) else None) for s, v in score.items()}
    return select_long_short(negated, k=k)


def _zscore(row: pd.Series) -> dict[str, float | None]:
    values = row.dropna()
    if len(values) < 2 or values.std(ddof=0) == 0:
        return {s: None for s in row.index}
    mean, std = values.mean(), values.std(ddof=0)
    return {s: (float((row[s] - mean) / std) if pd.notna(row[s]) else None) for s in row.index}


def _backtest_signal(
    name: str,
    score_panel: pd.DataFrame,
    logp: pd.DataFrame,
    rebal: list[pd.Timestamp],
) -> tuple[object, list[tuple[datetime, float]]]:
    gross_returns: list[float] = []
    turnovers: list[float] = []
    dated_net: list[tuple[datetime, float]] = []
    prev_holdings: set[str] = set()
    round_trip = COST_BPS / 10_000.0
    for current, nxt in zip(rebal[:-1], rebal[1:], strict=False):
        score = {s: (float(v) if pd.notna(v) else None) for s, v in score_panel.loc[current].items()}
        forward = {
            s: (float(logp.loc[nxt, s] - logp.loc[current, s]) if pd.notna(logp.loc[nxt, s]) and pd.notna(logp.loc[current, s]) else None)
            for s in logp.columns
        }
        long, short = _select_top_bottom(score, REBAL_K)
        gross = gross_period_return(long, short, forward)
        if gross is None:
            continue
        holdings = set(long) | set(short)
        turnover = one_way_turnover(prev_holdings, holdings)
        prev_holdings = holdings
        gross_returns.append(gross)
        turnovers.append(turnover)
        dated_net.append(
            (
                datetime(nxt.year, nxt.month, nxt.day, tzinfo=timezone.utc),
                gross - turnover * round_trip,
            )
        )
    report = run_xs_backtest(
        name,
        gross_returns,
        turnovers,
        quantile_k=REBAL_K,
        cost_bps=COST_BPS,
        periods_per_year=PERIODS_PER_YEAR,
        trials=TRIALS,
    )
    return report, dated_net


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-sectional carry long-short backtest (SHFE)")
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    by_variety = _load_or_fetch(args.start_year, args.end_year)
    print(f"varieties: {sorted(by_variety)}")

    carry = pd.DataFrame({v: _carry_series(bars) for v, bars in by_variety.items()}).sort_index()
    logp = pd.DataFrame(
        {v: _continuous_logp(bars) for v, bars in by_variety.items()}
    ).sort_index()
    carry = carry.reindex(logp.index).ffill(limit=5)  # carry persists; allow short staleness
    mom_120 = logp - logp.shift(120)

    rebal = _month_end_dates(logp.index)
    print(f"panel: {logp.shape[1]} SHFE varieties x {logp.shape[0]} days, {len(rebal)} monthly rebalances\n")

    # expected-return scores (higher = expected to rise): carry as-is; reversal = -momentum
    carry_score = carry
    reversal_score = -mom_120.where(mom_120.abs() <= MAX_ABS_MOM)
    composite_score = pd.DataFrame(
        {
            ts: {
                s: (
                    (cz + rz) / 2
                    if (cz := _zscore(carry_score.loc[ts]).get(s)) is not None
                    and (rz := _zscore(reversal_score.loc[ts]).get(s)) is not None
                    else None
                )
                for s in logp.columns
            }
            for ts in rebal
        }
    ).T

    signals = {
        "carry": carry_score,
        "reversal(-mom120)": reversal_score,
        "carry+reversal_z": composite_score,
    }
    returns_by_signal: dict[str, list[tuple[datetime, float]]] = {}
    print(f"{'signal':<20}{'n':>4}{'net/mo':>9}{'win':>7}{'sharpe':>8}{'deflated':>10}{'p':>8}{'turn':>7}")
    runs: list[tuple[str, object]] = [
        (name, _backtest_signal(name, panel, logp, rebal)) for name, panel in signals.items()
    ]
    # full-cross-section rank-weighted carry — harvests breadth the k-cut throws away
    runs.append(("carry_rankwt", _backtest_rank_weighted("carry_rankwt", carry_score, logp, rebal)))
    for name, (report, dated_net) in runs:
        returns_by_signal[name] = dated_net
        if report.deflated is None:
            print(f"{name:<20}{report.periods:>4}  (insufficient)")
            continue
        gate = "  PASS" if report.has_significant_edge else ""
        print(
            f"{name:<20}{report.periods:>4}{report.net_mean_return * 100:>+8.2f}%"
            f"{report.win_rate * 100:>6.0f}%{report.sharpe:>+8.2f}"
            f"{report.deflated.deflated_sharpe:>+10.2f}{report.deflated.deflated_pvalue:>8.3f}"
            f"{(report.avg_turnover or 0) * 100:>6.0f}%{gate}"
        )

    print("\n=== carry (rank-weighted) sub-period consistency (net) ===")
    for block in sub_period_breakdown(
        returns_by_signal["carry_rankwt"], n_blocks=4, periods_per_year=PERIODS_PER_YEAR
    ):
        print(
            f"  {block.label}  n={block.periods:>3}  mean={block.mean_return * 100:+.2f}%/mo  "
            f"win={block.win_rate * 100:.0f}%  sharpe={block.sharpe:+.2f}"
        )

    print("\n=== walk-forward OOS (select best of {carry, rankwt, reversal, composite} on trailing 36mo) ===")
    wf = walk_forward_oos(returns_by_signal, train=36, test=12, periods_per_year=PERIODS_PER_YEAR)
    if wf.oos_deflated is not None:
        verdict = "SIGNIFICANT OOS" if wf.has_significant_edge else "not significant OOS"
        print(
            f"  oos n={wf.oos_periods}  mean={wf.oos_mean_return * 100:+.2f}%/mo  "
            f"win={wf.oos_win_rate * 100:.0f}%  sharpe={wf.oos_sharpe:+.2f}  "
            f"deflated={wf.oos_deflated.deflated_sharpe:+.2f} (p={wf.oos_deflated.deflated_pvalue:.3f}) -> {verdict}"
        )
        print(f"  selections: {[f'{d}:{s}' for d, s in wf.selections]}")
    else:
        print("  insufficient OOS periods")


if __name__ == "__main__":
    main()
