"""Relative-value (spread mean-reversion) replay backtest.

The ``spread_anomaly`` / ``basis_shift`` evaluators are dormant: nothing in the
backend computes the ``spread_stats`` (z-score / ADF / half-life) they need, so
they essentially never fire (1 each in 1721 historical signals). To test whether
the relative-value family has any edge we build the spread statistics from
scratch over the backfilled price history and backtest a simple z-score
reversion rule.

For each economically-linked pair we form the log-ratio spread ``s = ln(P1/P2)``,
compute a rolling **point-in-time** z-score (trailing window only), and on each
fresh crossing of ``|z|`` above an entry threshold emit a reversion bet — short
the spread when z>0, long when z<0. The spread's forward log-change over a fixed
horizon is the trade's return; costs are doubled (two legs). A per-pair ADF
p-value over the full series is reported as a mean-reversion diagnostic only (it
is NOT used for entry, to avoid look-ahead).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, pstdev

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    benjamini_hochberg_fdr,
    deflated_sharpe_ratio,
    sharpe_ratio,
)
from app.services.backtest.path_metrics import PathMetrics, calculate_path_metrics
from app.services.backtest.replay import load_main_series
from app.services.backtest.signal_backtest import default_round_trip_cost_bps
from app.services.signals.types import MarketBar

# Economically-linked, same-chain pairs where the spread can plausibly revert.
DEFAULT_PAIRS: tuple[tuple[str, str], ...] = (
    ("RB", "HC"),  # rebar vs hot-rolled coil
    ("I", "RB"),  # iron ore vs rebar
    ("J", "JM"),  # coke vs coking coal
    ("M", "Y"),  # soybean meal vs soybean oil
    ("Y", "P"),  # soybean oil vs palm oil
    ("CU", "AL"),  # copper vs aluminium
    ("CU", "ZN"),  # copper vs zinc
    ("AL", "ZN"),  # aluminium vs zinc
    ("AU", "AG"),  # gold vs silver
    ("TA", "MA"),  # PTA vs methanol
    ("PP", "MA"),  # polypropylene vs methanol
    ("RU", "NR"),  # natural rubber vs TSR20
)

Z_WINDOW = 60
ENTRY_Z = 2.0
HORIZONS: tuple[int, ...] = (1, 5, 20)
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class SpreadTrade:
    pair: str
    entry_date: datetime
    entry_z: float
    bet_sign: int  # -1 short the spread (z>0), +1 long the spread (z<0)
    forward_spread_return: dict[int, float | None]


@dataclass(frozen=True, slots=True)
class PairEdge:
    pair: str
    trades: int
    adf_pvalue: float | None
    win_rate: float | None
    mean_net_return: float | None
    raw_sharpe: float | None
    deflated: DeflatedSharpeResult | None
    fdr_rejected: bool | None
    fdr_adjusted_pvalue: float | None

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "trades": self.trades,
            "adf_pvalue": _round_opt(self.adf_pvalue),
            "win_rate": _round_opt(self.win_rate),
            "mean_net_return": _round_opt(self.mean_net_return),
            "raw_sharpe": _round_opt(self.raw_sharpe),
            "deflated": self.deflated.to_dict() if self.deflated else None,
            "fdr_rejected": self.fdr_rejected,
            "fdr_adjusted_pvalue": _round_opt(self.fdr_adjusted_pvalue),
        }


@dataclass(frozen=True, slots=True)
class SpreadBacktestReport:
    horizon_days: int
    round_trip_cost_bps: float
    total_trades: int
    portfolio_win_rate: float | None
    portfolio_mean_net_return: float | None
    portfolio_sharpe: float | None
    portfolio_deflated: DeflatedSharpeResult | None
    portfolio_path: PathMetrics | None
    per_pair: tuple[PairEdge, ...]

    @property
    def has_significant_edge(self) -> bool:
        return self.portfolio_deflated is not None and self.portfolio_deflated.passed_gate

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "round_trip_cost_bps": round(self.round_trip_cost_bps, 4),
            "total_trades": self.total_trades,
            "portfolio_win_rate": _round_opt(self.portfolio_win_rate),
            "portfolio_mean_net_return": _round_opt(self.portfolio_mean_net_return),
            "portfolio_sharpe": _round_opt(self.portfolio_sharpe),
            "portfolio_deflated": (
                self.portfolio_deflated.to_dict() if self.portfolio_deflated else None
            ),
            "portfolio_path": self.portfolio_path.to_dict() if self.portfolio_path else None,
            "has_significant_edge": self.has_significant_edge,
            "per_pair": [edge.to_dict() for edge in self.per_pair],
        }


def aligned_log_spread(
    bars1: list[MarketBar], bars2: list[MarketBar]
) -> tuple[list[datetime], list[float]]:
    """Log-ratio spread ln(P1/P2) on the common trading days of both legs."""

    by_day2 = {bar.timestamp.date(): bar.close for bar in bars2 if bar.close > 0}
    dates: list[datetime] = []
    spread: list[float] = []
    for bar in bars1:
        if bar.close <= 0:
            continue
        close2 = by_day2.get(bar.timestamp.date())
        if close2 is None or close2 <= 0:
            continue
        dates.append(bar.timestamp)
        spread.append(math.log(bar.close / close2))
    return dates, spread


def rolling_zscores(spread: list[float], window: int = Z_WINDOW) -> list[float | None]:
    """Point-in-time z-score: at index t use only spread[t-window+1 .. t]."""

    zscores: list[float | None] = []
    for index in range(len(spread)):
        if index < window - 1:
            zscores.append(None)
            continue
        window_values = spread[index - window + 1 : index + 1]
        mean = fmean(window_values)
        std = pstdev(window_values)
        zscores.append((spread[index] - mean) / std if std > 0 else None)
    return zscores


def detect_spread_trades(
    pair: str,
    dates: list[datetime],
    spread: list[float],
    zscores: list[float | None],
    *,
    entry_z: float = ENTRY_Z,
    horizons: tuple[int, ...] = HORIZONS,
) -> list[SpreadTrade]:
    trades: list[SpreadTrade] = []
    for index in range(1, len(spread)):
        current = zscores[index]
        previous = zscores[index - 1]
        if current is None or previous is None:
            continue
        crossed_high = previous <= entry_z < current
        crossed_low = previous >= -entry_z > current
        if not crossed_high and not crossed_low:
            continue
        bet_sign = -1 if crossed_high else 1  # short the spread when it is rich
        forward = {
            horizon: (spread[index + horizon] - spread[index] if index + horizon < len(spread) else None)
            for horizon in horizons
        }
        trades.append(
            SpreadTrade(
                pair=pair,
                entry_date=dates[index],
                entry_z=current,
                bet_sign=bet_sign,
                forward_spread_return=forward,
            )
        )
    return trades


def adf_pvalue(spread: list[float]) -> float | None:
    """Augmented Dickey-Fuller p-value (mean-reversion diagnostic, not an entry gate)."""

    if len(spread) < 40:
        return None
    try:
        from statsmodels.tsa.stattools import adfuller

        return float(adfuller(spread, autolag="AIC")[1])
    except Exception:
        return None


def _net_returns(trades: list[SpreadTrade], *, horizon: int, round_trip_cost: float) -> list[float]:
    nets: list[float] = []
    for trade in trades:
        forward = trade.forward_spread_return.get(horizon)
        if forward is None:
            continue
        nets.append(trade.bet_sign * forward - round_trip_cost)
    return nets


def _aggregate(nets: list[float], *, trials: int, horizon: int) -> tuple:
    if not nets:
        return None, None, None, None, None
    win_rate = sum(1 for value in nets if value > 0) / len(nets)
    mean_net = sum(nets) / len(nets)
    sharpe = deflated = path = None
    if len(nets) >= 2:
        periods = TRADING_DAYS_PER_YEAR / max(1, horizon)
        sharpe = sharpe_ratio(nets, periods_per_year=round(periods))
        deflated = deflated_sharpe_ratio(
            raw_sharpe=sharpe, returns_count=len(nets), trials=trials, periods_per_year=round(periods)
        )
        path = calculate_path_metrics(nets)
    return win_rate, mean_net, sharpe, deflated, path


def run_spread_backtest(
    trades_by_pair: dict[str, list[SpreadTrade]],
    *,
    adf_by_pair: dict[str, float | None] | None = None,
    horizon: int = 5,
    round_trip_cost_bps: float | None = None,
) -> SpreadBacktestReport:
    # two legs -> double the single-leg round-trip floor
    cost_bps = (2.0 * default_round_trip_cost_bps()) if round_trip_cost_bps is None else round_trip_cost_bps
    round_trip_cost = cost_bps / 10_000.0
    adf_by_pair = adf_by_pair or {}
    trials = max(1, len(trades_by_pair))

    edges: list[PairEdge] = []
    pending_pvalues: list[tuple[int, float]] = []
    portfolio: list[float] = []

    for pair in sorted(trades_by_pair):
        nets = _net_returns(trades_by_pair[pair], horizon=horizon, round_trip_cost=round_trip_cost)
        portfolio.extend(nets)
        win_rate, mean_net, sharpe, deflated, _ = _aggregate(nets, trials=trials, horizon=horizon)
        if deflated is not None:
            pending_pvalues.append((len(edges), deflated.deflated_pvalue))
        edges.append(
            PairEdge(
                pair=pair,
                trades=len(nets),
                adf_pvalue=adf_by_pair.get(pair),
                win_rate=win_rate,
                mean_net_return=mean_net,
                raw_sharpe=sharpe,
                deflated=deflated,
                fdr_rejected=None,
                fdr_adjusted_pvalue=None,
            )
        )

    if pending_pvalues:
        decisions = benjamini_hochberg_fdr([p for _, p in pending_pvalues])
        for (edge_index, _), decision in zip(pending_pvalues, decisions, strict=True):
            edge = edges[edge_index]
            edges[edge_index] = PairEdge(
                pair=edge.pair,
                trades=edge.trades,
                adf_pvalue=edge.adf_pvalue,
                win_rate=edge.win_rate,
                mean_net_return=edge.mean_net_return,
                raw_sharpe=edge.raw_sharpe,
                deflated=edge.deflated,
                fdr_rejected=decision.rejected,
                fdr_adjusted_pvalue=decision.adjusted_pvalue,
            )

    p_win, p_mean, p_sharpe, p_deflated, p_path = _aggregate(
        portfolio, trials=trials, horizon=horizon
    )
    return SpreadBacktestReport(
        horizon_days=horizon,
        round_trip_cost_bps=cost_bps,
        total_trades=len(portfolio),
        portfolio_win_rate=p_win,
        portfolio_mean_net_return=p_mean,
        portfolio_sharpe=p_sharpe,
        portfolio_deflated=p_deflated,
        portfolio_path=p_path,
        per_pair=tuple(edges),
    )


async def replay_spreads(
    session: AsyncSession,
    *,
    pairs: tuple[tuple[str, str], ...] = DEFAULT_PAIRS,
    entry_z: float = ENTRY_Z,
    window: int = Z_WINDOW,
    with_adf: bool = True,
    max_series_bars: int = 20000,
) -> tuple[dict[str, list[SpreadTrade]], dict[str, float | None]]:
    trades_by_pair: dict[str, list[SpreadTrade]] = {}
    adf_by_pair: dict[str, float | None] = {}
    series_cache: dict[str, list[MarketBar]] = {}

    async def series(symbol: str) -> list[MarketBar]:
        if symbol not in series_cache:
            series_cache[symbol] = await load_main_series(session, symbol, limit=max_series_bars)
        return series_cache[symbol]

    for leg1, leg2 in pairs:
        pair = f"{leg1}-{leg2}"
        dates, spread = aligned_log_spread(await series(leg1), await series(leg2))
        if len(spread) < window + max(HORIZONS):
            trades_by_pair[pair] = []
            adf_by_pair[pair] = None
            continue
        zscores = rolling_zscores(spread, window)
        trades_by_pair[pair] = detect_spread_trades(
            pair, dates, spread, zscores, entry_z=entry_z
        )
        adf_by_pair[pair] = adf_pvalue(spread) if with_adf else None

    return trades_by_pair, adf_by_pair


def _round_opt(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)
