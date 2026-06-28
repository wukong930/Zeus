"""CLI: relative-value (spread mean-reversion) backtest over the price history.

Tests whether the relative-value family has edge by building spread statistics
from scratch (the spread_anomaly/basis_shift evaluators are dormant shells with
no spread_stats producer) and backtesting a z-score reversion rule across
economically-linked pairs.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_spread_backtest
    .venv/bin/python -m app.tools.run_spread_backtest --entry-z 2.5 --horizon 20
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import AsyncSessionLocal
from app.services.backtest.spread_replay import (
    HORIZONS,
    SpreadBacktestReport,
    replay_spreads,
    run_spread_backtest,
)


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def _format(report: SpreadBacktestReport) -> str:
    lines: list[str] = []
    lines.append(
        f"\n=== horizon {report.horizon_days}d "
        f"(round-trip cost {report.round_trip_cost_bps:.1f} bps, 2 legs) ==="
    )
    lines.append(f"total spread trades: {report.total_trades}")
    lines.append("\n portfolio (all pairs, equal-weight reversion bets):")
    if report.total_trades:
        lines.append(f"   win rate            {_pct(report.portfolio_win_rate)}")
        lines.append(
            f"   mean net return     {report.portfolio_mean_net_return * 100:+.3f}%"
            if report.portfolio_mean_net_return is not None
            else "   mean net return      n/a"
        )
        if report.portfolio_deflated is not None:
            d = report.portfolio_deflated
            lines.append(
                f"   sharpe {report.portfolio_sharpe:.2f}  |  deflated {d.deflated_sharpe:.2f} "
                f"(p={d.deflated_pvalue:.3f}, trials={d.trials})"
            )
        verdict = "SIGNIFICANT edge" if report.has_significant_edge else "NO significant edge"
        lines.append(f"   verdict: {verdict} after costs (Deflated Sharpe gate)")

    lines.append("\n per pair (adf_p < 0.05 => mean-reverting series):")
    lines.append(f"   {'pair':<10}{'n':>5}{'adf_p':>8}{'win':>8}{'mean net':>11}{'fdr':>6}")
    for edge in sorted(report.per_pair, key=lambda e: -(e.mean_net_return or -9)):
        mean_net = "n/a" if edge.mean_net_return is None else f"{edge.mean_net_return * 100:+.3f}%"
        adf = "n/a" if edge.adf_pvalue is None else f"{edge.adf_pvalue:.3f}"
        fdr = "—" if edge.fdr_rejected is None else ("rej" if edge.fdr_rejected else "no")
        lines.append(
            f"   {edge.pair:<10}{edge.trades:>5}{adf:>8}{_pct(edge.win_rate):>8}{mean_net:>11}{fdr:>6}"
        )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Spread mean-reversion backtest over history")
    parser.add_argument("--horizon", type=int, choices=HORIZONS, default=None)
    parser.add_argument("--entry-z", type=float, default=2.0, help="z-score entry threshold")
    parser.add_argument("--cost-bps", type=float, default=None, help="round-trip cost (bps, 2 legs)")
    parser.add_argument("--no-adf", action="store_true", help="skip the ADF diagnostic")
    args = parser.parse_args()

    print("replaying spread pairs over backfilled history ...")
    async with AsyncSessionLocal() as session:
        trades_by_pair, adf_by_pair = await replay_spreads(
            session, entry_z=args.entry_z, with_adf=not args.no_adf
        )

    total = sum(len(trades) for trades in trades_by_pair.values())
    print(f"pairs: {len(trades_by_pair)}  spread trades: {total}")

    horizons = (args.horizon,) if args.horizon else HORIZONS
    for horizon in horizons:
        report = run_spread_backtest(
            trades_by_pair,
            adf_by_pair=adf_by_pair,
            horizon=horizon,
            round_trip_cost_bps=args.cost_bps,
        )
        print(_format(report))
    print(
        "\nnote: log-ratio spread, point-in-time z-score, fixed-horizon hold. A real edge must "
        "clear the Deflated Sharpe gate after the 2-leg cost."
    )


if __name__ == "__main__":
    asyncio.run(main())
