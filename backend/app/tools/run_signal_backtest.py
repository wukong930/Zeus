"""CLI: run the out-of-sample, cost-aware signal backtest against the live DB.

This turns ``services/backtest/signal_backtest.py`` into something you can
actually point at your populated ``signal_track`` table to answer: *do the
existing directional signals have a tradable edge after costs?* It only reads
resolved signals — no writes, no migration.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_signal_backtest
    .venv/bin/python -m app.tools.run_signal_backtest --days 730 --horizon 20
    .venv/bin/python -m app.tools.run_signal_backtest --cost-bps 6 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.core.database import AsyncSessionLocal
from app.services.backtest.signal_backtest import BacktestReport, Horizon, run_backtest

HORIZONS: tuple[Horizon, ...] = (1, 5, 20)


def _format_pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def _format_report(report: BacktestReport) -> str:
    lines: list[str] = []
    lines.append(
        f"\n=== horizon {report.horizon_days}d "
        f"(round-trip cost {report.round_trip_cost_bps:.1f} bps) ==="
    )
    lines.append(f"signals analyzed: {report.total_signals}  |  by class: {report.count_by_class}")

    lines.append("\n hit rate by outcome semantics (NOT comparable across classes):")
    for semantics, rate in report.hit_rate_by_class.items():
        count = report.count_by_class.get(semantics, 0)
        lines.append(f"   {semantics:<14} {_format_pct(rate)}  (n={count})")

    lines.append("\n directional portfolio (the only tradable, cost-netted edge):")
    if report.directional_trades:
        lines.append(f"   trades                {report.directional_trades}")
        lines.append(f"   gross accuracy        {_format_pct(report.portfolio_gross_accuracy)}")
        lines.append(f"   cost-aware hit rate   {_format_pct(report.portfolio_cost_aware_hit_rate)}")
        lines.append(
            f"   mean net return/trade {report.portfolio_mean_net_return * 100:+.3f}%"
            if report.portfolio_mean_net_return is not None
            else "   mean net return/trade  n/a"
        )
        if report.portfolio_deflated is not None:
            d = report.portfolio_deflated
            lines.append(
                f"   sharpe {report.portfolio_sharpe:.2f}  |  deflated {d.deflated_sharpe:.2f} "
                f"(p={d.deflated_pvalue:.3f}, trials={d.trials})"
            )
        verdict = "SIGNIFICANT edge" if report.has_significant_edge else "NO significant edge"
        lines.append(f"   verdict: {verdict} after costs (Deflated Sharpe gate)")
    else:
        lines.append("   (no resolved directional signals in window)")

    scored = [e for e in report.per_signal if e.scored_trades]
    if scored:
        lines.append("\n per directional signal type:")
        lines.append(f"   {'signal':<24}{'n':>5}{'gross':>8}{'net hit':>9}{'mean net':>11}{'fdr':>6}")
        for edge in sorted(scored, key=lambda e: -(e.mean_net_return or 0)):
            mean_net = "n/a" if edge.mean_net_return is None else f"{edge.mean_net_return * 100:+.3f}%"
            fdr = "—" if edge.fdr_rejected is None else ("rej" if edge.fdr_rejected else "no")
            lines.append(
                f"   {edge.signal_type:<24}{edge.scored_trades:>5}"
                f"{_format_pct(edge.gross_directional_accuracy):>8}"
                f"{_format_pct(edge.cost_aware_hit_rate):>9}{mean_net:>11}{fdr:>6}"
            )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Out-of-sample cost-aware signal backtest")
    parser.add_argument("--days", type=int, default=365, help="lookback window in days")
    parser.add_argument(
        "--horizon",
        type=int,
        choices=HORIZONS,
        default=None,
        help="single horizon; default runs 1/5/20",
    )
    parser.add_argument("--cost-bps", type=float, default=None, help="round-trip cost override (bps)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    horizons = (args.horizon,) if args.horizon else HORIZONS

    reports: dict[int, BacktestReport] = {}
    async with AsyncSessionLocal() as session:
        for horizon in horizons:
            reports[horizon] = await run_backtest(
                session,
                horizon=horizon,
                start=start,
                end=end,
                round_trip_cost_bps=args.cost_bps,
            )

    if args.json:
        print(
            json.dumps(
                {
                    "window": {"start": start.isoformat(), "end": end.isoformat()},
                    "reports": {str(h): r.to_dict() for h, r in reports.items()},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"window: {start.date()} → {end.date()}  ({args.days}d lookback)")
    for horizon in horizons:
        print(_format_report(reports[horizon]))
    print(
        "\nnote: 'gross' = direction correct before cost; 'net hit' = profitable after the "
        "round-trip slippage floor. A real edge must clear the Deflated Sharpe gate, not just >50%."
    )


if __name__ == "__main__":
    asyncio.run(main())
