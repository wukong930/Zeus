"""Shadow tracking for the governed forecast signal.

Records the forecast's realized performance over time — what the dollar-neutral
target portfolio WOULD have made over its holding horizon — without touching
production. Once a forecast's horizon elapses and the forward data exists, its
``realized_return`` is filled in; ``shadow_performance`` aggregates the resolved
track into mean / win-rate / Sharpe / Deflated Sharpe so the signal accumulates
a live, auditable record before any governance promotion.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import ForecastRecord
from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    deflated_sharpe_ratio,
    sharpe_ratio,
)
from app.services.backtest.replay import load_main_series

MAX_ABS_RETURN = 0.5
DEFAULT_PERIODS_PER_YEAR = 12


@dataclass(frozen=True, slots=True)
class ShadowScoringResult:
    scanned: int
    resolved: int
    pending: int


@dataclass(frozen=True, slots=True)
class ShadowPerformance:
    signal: str
    resolved: int
    mean_return: float | None
    win_rate: float | None
    sharpe: float | None
    deflated: DeflatedSharpeResult | None

    def to_dict(self) -> dict:
        return {
            "signal": self.signal,
            "resolved": self.resolved,
            "mean_return": None if self.mean_return is None else round(self.mean_return, 6),
            "win_rate": None if self.win_rate is None else round(self.win_rate, 4),
            "sharpe": None if self.sharpe is None else round(self.sharpe, 4),
            "deflated": self.deflated.to_dict() if self.deflated else None,
        }


def weighted_realized_return(
    weights: dict[str, float],
    returns_by_symbol: dict[str, float | None],
    *,
    max_abs_return: float = MAX_ABS_RETURN,
) -> float | None:
    """Σ weight·return; None if any leg is unpriced (forward data not yet available)."""

    total = 0.0
    for symbol, weight in weights.items():
        symbol_return = returns_by_symbol.get(symbol)
        if symbol_return is None:
            return None
        clipped = 0.0 if abs(symbol_return) > max_abs_return else symbol_return  # drop roll artifacts
        total += float(weight) * clipped
    return total


def _holding_return(dates: list[datetime], closes: list[float], as_of: datetime, horizon: int) -> float | None:
    entry_index = bisect_right(dates, as_of) - 1  # last bar at/before as_of
    if entry_index < 0:
        return None
    exit_index = entry_index + horizon
    if exit_index >= len(closes):
        return None  # holding period not elapsed in the data yet
    entry = closes[entry_index]
    if entry <= 0:
        return None
    return (closes[exit_index] - entry) / entry


async def score_due_forecasts(
    session: AsyncSession,
    *,
    now: datetime,
    signal: str | None = None,
    limit: int = 1000,
) -> ShadowScoringResult:
    statement = select(ForecastRecord).where(ForecastRecord.realized_return.is_(None))
    if signal is not None:
        statement = statement.where(ForecastRecord.signal == signal)
    statement = statement.order_by(ForecastRecord.as_of.asc()).limit(limit)
    forecasts = list((await session.scalars(statement)).all())

    cache: dict[str, tuple[list[datetime], list[float]]] = {}

    async def series(symbol: str) -> tuple[list[datetime], list[float]]:
        if symbol not in cache:
            bars = await load_main_series(session, symbol)
            cache[symbol] = ([bar.timestamp for bar in bars], [bar.close for bar in bars])
        return cache[symbol]

    resolved = pending = 0
    for forecast in forecasts:
        weights = forecast.target_weights or {}
        if not weights:
            pending += 1
            continue
        returns: dict[str, float | None] = {}
        for symbol in weights:
            dates, closes = await series(symbol)
            returns[symbol] = _holding_return(dates, closes, forecast.as_of, forecast.horizon_days)
        realized = weighted_realized_return(weights, returns)
        if realized is None:
            pending += 1
            continue
        forecast.realized_return = realized
        forecast.resolved_at = now
        resolved += 1

    await session.flush()
    return ShadowScoringResult(scanned=len(forecasts), resolved=resolved, pending=pending)


async def shadow_performance(
    session: AsyncSession,
    *,
    signal: str,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> ShadowPerformance:
    statement = (
        select(ForecastRecord)
        .where(ForecastRecord.signal == signal, ForecastRecord.realized_return.is_not(None))
        .order_by(ForecastRecord.as_of.asc())
    )
    rows = list((await session.scalars(statement)).all())
    returns = [float(row.realized_return) for row in rows if row.realized_return is not None]
    n = len(returns)
    if n == 0:
        return ShadowPerformance(signal, 0, None, None, None, None)
    mean = sum(returns) / n
    win_rate = sum(1 for value in returns if value > 0) / n
    sharpe = sharpe_ratio(returns, periods_per_year=periods_per_year) if n >= 2 else 0.0
    deflated = (
        deflated_sharpe_ratio(
            raw_sharpe=sharpe, returns_count=n, trials=1, periods_per_year=periods_per_year
        )
        if n >= 2
        else None
    )
    return ShadowPerformance(signal, n, mean, win_rate, sharpe, deflated)
