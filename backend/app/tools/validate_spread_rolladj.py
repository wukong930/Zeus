"""Validate the 20d spread edge against contract-roll bias.

Fetches per-contract daily data (get_futures_daily) for SHFE+DCE over a
multi-regime window, builds BOTH a roll-free back-adjusted continuous series and
the raw (gap-laden) dominant-contract stitch from the same data, then runs the
spread mean-reversion backtest on each for within-market pairs. If the 20d edge
survives back-adjustment it is real; if it collapses it was a roll artifact.

Usage (from backend/, no DB needed — fetches AKShare directly):
    .venv/bin/python -m app.tools.validate_spread_rolladj --start-year 2018
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone

from app.services.backtest.roll_adjust import (
    ContractBar,
    back_adjusted_closes,
    raw_continuous_closes,
)
from app.services.backtest.spread_replay import (
    HORIZONS,
    aligned_log_spread,
    detect_spread_trades,
    rolling_zscores,
    run_spread_backtest,
)
from app.services.signals.types import MarketBar

# within-market pairs (both legs on the fetched markets) — the strongest 20d edges
VALIDATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("RB", "HC"),
    ("AL", "ZN"),
    ("CU", "AL"),
    ("CU", "ZN"),
    ("AU", "AG"),
    ("J", "JM"),
    ("M", "Y"),
    ("Y", "P"),
)
MARKETS = ("SHFE", "DCE")
VARIETIES = {"RB", "HC", "AL", "ZN", "CU", "AU", "AG", "J", "JM", "M", "Y", "P"}


def _fetch_contract_bars(start_year: int, end_year: int) -> dict[str, list[ContractBar]]:
    import akshare as ak

    by_variety: dict[str, list[ContractBar]] = defaultdict(list)
    for market in MARKETS:
        for year in range(start_year, end_year + 1):
            try:
                frame = ak.get_futures_daily(
                    start_date=f"{year}0101", end_date=f"{year}1231", market=market
                )
            except Exception as exc:
                print(f"  fetch {market} {year} ERROR: {repr(exc)[:100]}")
                continue
            count = 0
            for row in frame.itertuples(index=False):
                variety = str(getattr(row, "variety", "") or "").upper()
                if variety not in VARIETIES:
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
            print(f"  fetched {market} {year}: {count} relevant contract-bars")
    return by_variety


def _to_bars(closes: list[tuple]) -> list[MarketBar]:
    return [
        MarketBar(
            timestamp=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for day, close in closes
    ]


def _run(series_by_symbol: dict[str, list[MarketBar]], label: str) -> None:
    trades_by_pair: dict[str, list] = {}
    for leg1, leg2 in VALIDATION_PAIRS:
        if leg1 not in series_by_symbol or leg2 not in series_by_symbol:
            continue
        pair = f"{leg1}-{leg2}"
        dates, spread = aligned_log_spread(series_by_symbol[leg1], series_by_symbol[leg2])
        if len(spread) < 80:
            trades_by_pair[pair] = []
            continue
        zscores = rolling_zscores(spread)
        trades_by_pair[pair] = detect_spread_trades(pair, dates, spread, zscores, entry_z=2.0)

    total = sum(len(trades) for trades in trades_by_pair.values())
    print(f"\n########## {label} ##########")
    print(f"pairs: {len(trades_by_pair)}  spread trades: {total}")
    for horizon in HORIZONS:
        report = run_spread_backtest(trades_by_pair, horizon=horizon)
        if not report.total_trades or report.portfolio_deflated is None:
            print(f"  h={horizon}: no trades")
            continue
        d = report.portfolio_deflated
        verdict = "SIGNIFICANT edge" if report.has_significant_edge else "no significant edge"
        print(
            f"  h={horizon:>2}d  win={report.portfolio_win_rate * 100:4.1f}%  "
            f"mean_net={report.portfolio_mean_net_return * 100:+.3f}%  "
            f"sharpe={report.portfolio_sharpe:+.2f}  "
            f"deflated={d.deflated_sharpe:+.2f} (p={d.deflated_pvalue:.3f})  -> {verdict}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate spread edge vs contract-roll bias")
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    print(f"fetching per-contract data {args.start_year}-{args.end_year} for {MARKETS} ...")
    by_variety = _fetch_contract_bars(args.start_year, args.end_year)
    print(f"varieties fetched: {sorted(by_variety)}")

    adjusted = {v: _to_bars(back_adjusted_closes(bars)) for v, bars in by_variety.items()}
    raw = {v: _to_bars(raw_continuous_closes(bars)) for v, bars in by_variety.items()}

    _run(raw, "RAW continuous (roll gaps intact)")
    _run(adjusted, "BACK-ADJUSTED (roll-free)")
    print("\nIf the 20d edge survives back-adjustment it is real; if it collapses it was roll bias.")


if __name__ == "__main__":
    main()
