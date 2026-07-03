"""Live-divergence auto-demote — the forecast kill switch.

Once a forecast signal is authoritative, its LIVE realized performance is
watched against expectation. If the live track breaks (negative Sharpe over
enough periods, or a drawdown breach), the signal is automatically demoted back
to shadow — unilaterally, because demotion only REDUCES risk. Re-promotion must
go through governance again (risk-increasing changes stay governed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.models.forecast import ForecastRecord
from app.services.backtest.multiple_testing import sharpe_ratio
from app.services.prediction.governance import FORECAST_PROMOTION_SOURCE, promotion_key

DEFAULT_MIN_LIVE_PERIODS = 10
DEFAULT_MIN_LIVE_SHARPE = 0.0
DEFAULT_MAX_DRAWDOWN = 0.10
PERIODS_PER_YEAR = 12


@dataclass(frozen=True, slots=True)
class LivePerformance:
    periods: int
    mean_return: float
    sharpe: float
    max_drawdown: float


@dataclass(frozen=True, slots=True)
class DivergenceResult:
    performance: LivePerformance
    breached: bool
    reason: str | None
    demoted: bool


def live_performance_from_returns(returns: list[float]) -> LivePerformance:
    n = len(returns)
    if n == 0:
        return LivePerformance(0, 0.0, 0.0, 0.0)
    mean = sum(returns) / n
    sharpe = sharpe_ratio(returns, periods_per_year=PERIODS_PER_YEAR) if n >= 2 else 0.0
    cumulative = peak = max_drawdown = 0.0
    for value in returns:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return LivePerformance(n, mean, sharpe, max_drawdown)


def assess_divergence(
    performance: LivePerformance,
    *,
    min_live_periods: int = DEFAULT_MIN_LIVE_PERIODS,
    min_live_sharpe: float = DEFAULT_MIN_LIVE_SHARPE,
    max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
) -> tuple[bool, str | None]:
    if performance.periods < min_live_periods:
        return False, None  # insufficient live track — don't act on noise
    if performance.sharpe < min_live_sharpe:
        return True, f"live sharpe {performance.sharpe:.2f} below floor {min_live_sharpe:.2f}"
    if performance.max_drawdown < -max_drawdown:
        return True, f"live drawdown {performance.max_drawdown:.3f} breached -{max_drawdown:.3f}"
    return False, None


async def live_performance(session: AsyncSession, *, signal: str) -> LivePerformance:
    rows = list(
        (
            await session.scalars(
                select(ForecastRecord)
                .where(
                    ForecastRecord.signal == signal,
                    ForecastRecord.decision_grade.is_(True),
                    ForecastRecord.realized_return.is_not(None),
                )
                .order_by(ForecastRecord.as_of.asc())
            )
        ).all()
    )
    return live_performance_from_returns(
        [float(row.realized_return) for row in rows if row.realized_return is not None]
    )


async def demote_signal(
    session: AsyncSession, *, signal: str, model_version: str, reason: str
) -> bool:
    row = (
        await session.scalars(
            select(ChangeReviewQueue)
            .where(
                ChangeReviewQueue.source == FORECAST_PROMOTION_SOURCE,
                ChangeReviewQueue.target_key == promotion_key(signal, model_version),
                ChangeReviewQueue.status == "approved",
            )
            .limit(1)
        )
    ).first()
    if row is None:
        return False
    row.status = "demoted"
    payload = dict(row.proposed_change or {})
    payload["demotion"] = {"reason": reason, "demoted_at": datetime.now(UTC).isoformat()}
    row.proposed_change = payload
    await session.flush()
    return True


async def evaluate_and_demote(
    session: AsyncSession,
    *,
    signal: str,
    model_version: str,
    min_live_periods: int = DEFAULT_MIN_LIVE_PERIODS,
    min_live_sharpe: float = DEFAULT_MIN_LIVE_SHARPE,
    max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
) -> DivergenceResult:
    performance = await live_performance(session, signal=signal)
    breached, reason = assess_divergence(
        performance,
        min_live_periods=min_live_periods,
        min_live_sharpe=min_live_sharpe,
        max_drawdown=max_drawdown,
    )
    demoted = False
    if breached and reason is not None:
        demoted = await demote_signal(
            session, signal=signal, model_version=model_version, reason=reason
        )
    return DivergenceResult(performance, breached, reason, demoted)
