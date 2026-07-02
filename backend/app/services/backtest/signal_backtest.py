"""Out-of-sample, cost-aware backtest over historically emitted signals.

This module answers the platform's pivotal question: *do the existing
directional signals have a real, tradable edge after costs?* It does NOT train
a model and introduces no production mutation. It replays resolved
``SignalTrack`` rows (which already store the realized point-in-time forward
returns and the per-signal outcome) and reports, per signal type and for the
directional portfolio:

* cost-aware directional hit rate and mean net return (net of a round-trip
  slippage floor sourced from ``slippage.BASE_SLIPPAGE_BPS_BY_TIER``),
* Sharpe and **Deflated Sharpe** (deflated by the number of signal families
  tried — the anti data-snooping gate), with FDR control across families,
* path metrics (drawdown / CVaR).

Crucially, hit rate is reported **split by outcome semantics**. Only
``directional`` signals assert a price direction and feed the net-return
backtest; ``mean_reversion`` (spread reverts) and ``volatility`` (range / vol
expands) signals assert something else entirely, so folding them into one
"accuracy" number is a category error. Their stored hit rate is still reported,
but in its own bucket.

The split between the pure ``run_signal_backtest`` and the thin async loader
keeps the statistics offline-testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import SignalTrack
from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    benjamini_hochberg_fdr,
    deflated_sharpe_ratio,
    sharpe_ratio,
)
from app.services.backtest.path_metrics import PathMetrics, calculate_path_metrics
from app.services.backtest.slippage import BASE_SLIPPAGE_BPS_BY_TIER
from app.services.signals.semantics import OutcomeSemantics, classify_semantics

Horizon = Literal[1, 5, 20]

TRADING_DAYS_PER_YEAR = 252

# Signal outcome semantics (directional / mean_reversion / volatility) live in
# app/services/signals/semantics.py — the single source of truth shared with the
# live calibration hit-rate breakdown — and are imported above.

# Natural scoring horizon per signal, mirroring the horizon each evaluator uses
# for its own outcome. Used only as the default when the caller does not pin a
# single horizon for the whole run.
DEFAULT_HORIZON_BY_SIGNAL: dict[str, Horizon] = {
    "momentum": 20,
    "basis_shift": 20,
    "price_gap": 5,
    "event_driven": 5,
    "news_event": 5,
    "rubber_supply_shock": 20,
    "capacity_contraction": 20,
    "marginal_capacity_squeeze": 20,
    "median_pressure": 20,
    "restart_expectation": 20,
    "spread_anomaly": 20,
    "regime_shift": 20,
    "inventory_shock": 5,
}


def default_round_trip_cost_bps() -> float:
    """Round-trip slippage floor for a liquid main contract (entry + exit).

    Sourced from the project's own slippage model rather than a magic number.
    It is a *floor*: real costs rise with the vol / liquidity / time-of-day
    multipliers in ``slippage.calculate_slippage``.
    """

    return 2.0 * BASE_SLIPPAGE_BPS_BY_TIER["main"]


@dataclass(frozen=True, slots=True)
class BacktestSignal:
    """A resolved historical signal — the unit the backtest replays."""

    signal_type: str
    direction: str | None
    outcome: str
    forward_return_1d: float | None = None
    forward_return_5d: float | None = None
    forward_return_20d: float | None = None
    created_at: datetime | None = None

    def forward_return(self, horizon: Horizon) -> float | None:
        if horizon == 1:
            return self.forward_return_1d
        if horizon == 5:
            return self.forward_return_5d
        return self.forward_return_20d


@dataclass(frozen=True, slots=True)
class SignalEdge:
    signal_type: str
    semantics: OutcomeSemantics
    sample_size: int
    resolved_count: int
    stored_hit_rate: float | None
    scored_trades: int
    gross_directional_accuracy: float | None
    cost_aware_hit_rate: float | None
    mean_net_return: float | None
    raw_sharpe: float | None
    deflated: DeflatedSharpeResult | None
    fdr_rejected: bool | None
    fdr_adjusted_pvalue: float | None

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "semantics": self.semantics,
            "sample_size": self.sample_size,
            "resolved_count": self.resolved_count,
            "stored_hit_rate": _round_opt(self.stored_hit_rate),
            "scored_trades": self.scored_trades,
            "gross_directional_accuracy": _round_opt(self.gross_directional_accuracy),
            "cost_aware_hit_rate": _round_opt(self.cost_aware_hit_rate),
            "mean_net_return": _round_opt(self.mean_net_return),
            "raw_sharpe": _round_opt(self.raw_sharpe),
            "deflated": self.deflated.to_dict() if self.deflated else None,
            "fdr_rejected": self.fdr_rejected,
            "fdr_adjusted_pvalue": _round_opt(self.fdr_adjusted_pvalue),
        }


@dataclass(frozen=True, slots=True)
class BacktestReport:
    horizon_days: int
    round_trip_cost_bps: float
    total_signals: int
    count_by_class: dict[str, int]
    hit_rate_by_class: dict[str, float | None]
    directional_trades: int
    portfolio_gross_accuracy: float | None
    portfolio_cost_aware_hit_rate: float | None
    portfolio_mean_net_return: float | None
    portfolio_sharpe: float | None
    portfolio_deflated: DeflatedSharpeResult | None
    portfolio_path: PathMetrics | None
    per_signal: tuple[SignalEdge, ...]

    @property
    def has_significant_edge(self) -> bool:
        """True only if the directional portfolio clears the Deflated Sharpe gate."""

        return self.portfolio_deflated is not None and self.portfolio_deflated.passed_gate

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "round_trip_cost_bps": round(self.round_trip_cost_bps, 4),
            "total_signals": self.total_signals,
            "count_by_class": dict(self.count_by_class),
            "hit_rate_by_class": {k: _round_opt(v) for k, v in self.hit_rate_by_class.items()},
            "directional_trades": self.directional_trades,
            "portfolio_gross_accuracy": _round_opt(self.portfolio_gross_accuracy),
            "portfolio_cost_aware_hit_rate": _round_opt(self.portfolio_cost_aware_hit_rate),
            "portfolio_mean_net_return": _round_opt(self.portfolio_mean_net_return),
            "portfolio_sharpe": _round_opt(self.portfolio_sharpe),
            "portfolio_deflated": (
                self.portfolio_deflated.to_dict() if self.portfolio_deflated else None
            ),
            "portfolio_path": self.portfolio_path.to_dict() if self.portfolio_path else None,
            "has_significant_edge": self.has_significant_edge,
            "per_signal": [edge.to_dict() for edge in self.per_signal],
        }


def direction_sign(direction: str | None) -> int:
    if direction == "bullish":
        return 1
    if direction == "bearish":
        return -1
    return 0


def net_directional_return(
    forward_return: float,
    direction: str | None,
    *,
    round_trip_cost: float,
) -> float | None:
    """Cost-netted return of taking the signal's stated direction for one trade.

    Returns ``None`` when the direction is unknown (cannot be traded), so the
    signal is excluded from the directional edge rather than silently treated
    as flat.
    """

    sign = direction_sign(direction)
    if sign == 0:
        return None
    return forward_return * sign - round_trip_cost


def annualization_periods(horizon_days: int) -> float:
    """Non-overlapping h-day periods per year, for annualizing per-trade Sharpe.

    Each scored signal is treated as one horizon-length holding period. This is
    a deliberate per-trade approximation (signals are not daily-rebalanced); the
    figure is reported alongside the Deflated Sharpe, which is the gate.
    """

    return TRADING_DAYS_PER_YEAR / max(1, horizon_days)


def run_signal_backtest(
    signals: list[BacktestSignal],
    *,
    horizon: Horizon = 5,
    round_trip_cost_bps: float | None = None,
) -> BacktestReport:
    cost_bps = default_round_trip_cost_bps() if round_trip_cost_bps is None else round_trip_cost_bps
    round_trip_cost = cost_bps / 10_000.0
    periods_per_year = annualization_periods(horizon)

    # Group once; everything downstream reads from these buckets.
    by_type: dict[str, list[BacktestSignal]] = {}
    for signal in signals:
        by_type.setdefault(signal.signal_type, []).append(signal)

    count_by_class: dict[str, int] = {}
    class_hits: dict[str, int] = {}
    class_resolved: dict[str, int] = {}
    for signal in signals:
        semantics = classify_semantics(signal.signal_type)
        count_by_class[semantics] = count_by_class.get(semantics, 0) + 1
        if signal.outcome in ("hit", "miss"):
            class_resolved[semantics] = class_resolved.get(semantics, 0) + 1
            if signal.outcome == "hit":
                class_hits[semantics] = class_hits.get(semantics, 0) + 1
    hit_rate_by_class: dict[str, float | None] = {
        semantics: (class_hits.get(semantics, 0) / resolved if resolved else None)
        for semantics, resolved in {**{k: 0 for k in count_by_class}, **class_resolved}.items()
    }

    directional_types = sorted(t for t in by_type if classify_semantics(t) == "directional")
    trials = max(1, len(directional_types))

    edges: list[SignalEdge] = []
    portfolio_net: list[float] = []
    portfolio_gross_hits = 0
    portfolio_scored = 0

    # First pass builds every edge and the portfolio return stream.
    pending_pvalues: list[tuple[int, float]] = []  # (edge index, deflated pvalue)
    for signal_type in sorted(by_type):
        rows = by_type[signal_type]
        semantics = classify_semantics(signal_type)
        resolved = [r for r in rows if r.outcome in ("hit", "miss")]
        stored_hits = sum(1 for r in resolved if r.outcome == "hit")
        stored_hit_rate = (stored_hits / len(resolved)) if resolved else None

        gross_accuracy: float | None = None
        cost_aware_hit_rate: float | None = None
        mean_net: float | None = None
        raw_sharpe: float | None = None
        deflated: DeflatedSharpeResult | None = None
        net_returns: list[float] = []

        if semantics == "directional":
            gross_hits = 0
            for row in rows:
                forward = row.forward_return(horizon)
                net = (
                    None
                    if forward is None
                    else net_directional_return(forward, row.direction, round_trip_cost=round_trip_cost)
                )
                if net is None or forward is None:
                    continue
                net_returns.append(net)
                if forward * direction_sign(row.direction) > 0:
                    gross_hits += 1
            scored = len(net_returns)
            if scored:
                gross_accuracy = gross_hits / scored
                cost_aware_hit_rate = sum(1 for n in net_returns if n > 0) / scored
                mean_net = sum(net_returns) / scored
                portfolio_net.extend(net_returns)
                portfolio_gross_hits += gross_hits
                portfolio_scored += scored
            if scored >= 2:
                raw_sharpe = sharpe_ratio(net_returns, periods_per_year=round(periods_per_year))
                deflated = deflated_sharpe_ratio(
                    raw_sharpe=raw_sharpe,
                    returns_count=scored,
                    trials=trials,
                    periods_per_year=round(periods_per_year),
                )
                pending_pvalues.append((len(edges), deflated.deflated_pvalue))

        edges.append(
            SignalEdge(
                signal_type=signal_type,
                semantics=semantics,
                sample_size=len(rows),
                resolved_count=len(resolved),
                stored_hit_rate=stored_hit_rate,
                scored_trades=len(net_returns),
                gross_directional_accuracy=gross_accuracy,
                cost_aware_hit_rate=cost_aware_hit_rate,
                mean_net_return=mean_net,
                raw_sharpe=raw_sharpe,
                deflated=deflated,
                fdr_rejected=None,
                fdr_adjusted_pvalue=None,
            )
        )

    # FDR control across the directional family, then graft the decisions back.
    if pending_pvalues:
        decisions = benjamini_hochberg_fdr([p for _, p in pending_pvalues])
        for (edge_index, _), decision in zip(pending_pvalues, decisions, strict=True):
            edges[edge_index] = replace(
                edges[edge_index],
                fdr_rejected=decision.rejected,
                fdr_adjusted_pvalue=decision.adjusted_pvalue,
            )

    portfolio_sharpe: float | None = None
    portfolio_deflated: DeflatedSharpeResult | None = None
    portfolio_path: PathMetrics | None = None
    if len(portfolio_net) >= 2:
        portfolio_sharpe = sharpe_ratio(portfolio_net, periods_per_year=round(periods_per_year))
        portfolio_deflated = deflated_sharpe_ratio(
            raw_sharpe=portfolio_sharpe,
            returns_count=len(portfolio_net),
            trials=trials,
            periods_per_year=round(periods_per_year),
        )
        portfolio_path = calculate_path_metrics(portfolio_net)

    return BacktestReport(
        horizon_days=horizon,
        round_trip_cost_bps=cost_bps,
        total_signals=len(signals),
        count_by_class=count_by_class,
        hit_rate_by_class=hit_rate_by_class,
        directional_trades=portfolio_scored,
        portfolio_gross_accuracy=(
            portfolio_gross_hits / portfolio_scored if portfolio_scored else None
        ),
        portfolio_cost_aware_hit_rate=(
            sum(1 for n in portfolio_net if n > 0) / len(portfolio_net) if portfolio_net else None
        ),
        portfolio_mean_net_return=(
            sum(portfolio_net) / len(portfolio_net) if portfolio_net else None
        ),
        portfolio_sharpe=portfolio_sharpe,
        portfolio_deflated=portfolio_deflated,
        portfolio_path=portfolio_path,
        per_signal=tuple(edges),
    )


def _backtest_signals_statement(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    signal_types: list[str] | None = None,
    before: datetime | None = None,
    before_id: UUID | None = None,
    limit: int = 5000,
) -> Select:
    statement = select(SignalTrack).where(SignalTrack.outcome != "pending")
    if start is not None:
        statement = statement.where(SignalTrack.created_at >= start)
    if end is not None:
        statement = statement.where(SignalTrack.created_at <= end)
    if signal_types:
        statement = statement.where(SignalTrack.signal_type.in_(signal_types))
    if before is not None:
        if before_id is not None:
            statement = statement.where(
                or_(
                    SignalTrack.created_at < before,
                    and_(SignalTrack.created_at == before, SignalTrack.id < before_id),
                )
            )
        else:
            statement = statement.where(SignalTrack.created_at < before)
    return statement.order_by(SignalTrack.created_at.asc(), SignalTrack.id.asc()).limit(limit)


async def load_backtest_signals(
    session: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    signal_types: list[str] | None = None,
    limit: int = 5000,
) -> list[BacktestSignal]:
    statement = _backtest_signals_statement(
        start=start,
        end=end,
        signal_types=signal_types,
        limit=limit,
    )
    rows = (await session.scalars(statement)).all()
    return [
        BacktestSignal(
            signal_type=row.signal_type,
            direction=row.direction,
            outcome=row.outcome,
            forward_return_1d=row.forward_return_1d,
            forward_return_5d=row.forward_return_5d,
            forward_return_20d=row.forward_return_20d,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def run_backtest(
    session: AsyncSession,
    *,
    horizon: Horizon = 5,
    start: datetime | None = None,
    end: datetime | None = None,
    signal_types: list[str] | None = None,
    round_trip_cost_bps: float | None = None,
    limit: int = 5000,
) -> BacktestReport:
    signals = await load_backtest_signals(
        session,
        start=start,
        end=end,
        signal_types=signal_types,
        limit=limit,
    )
    return run_signal_backtest(signals, horizon=horizon, round_trip_cost_bps=round_trip_cost_bps)


def _round_opt(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)
