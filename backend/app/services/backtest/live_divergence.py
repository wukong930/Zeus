from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.models.live_divergence_metrics import LiveDivergenceMetric


@dataclass(frozen=True, slots=True)
class DivergenceResult:
    metric_type: str
    backtest_value: float | None
    live_value: float | None
    tracking_error: float | None
    threshold: float
    severity: str
    reason: str
    details: dict

    @property
    def triggered(self) -> bool:
        return self.severity in {"yellow", "red"}

    def to_dict(self) -> dict:
        return {
            "metric_type": self.metric_type,
            "backtest_value": self.backtest_value,
            "live_value": self.live_value,
            "tracking_error": self.tracking_error,
            "threshold": self.threshold,
            "severity": self.severity,
            "reason": self.reason,
            "details": self.details,
        }


def tracking_error(
    theoretical_returns: list[float],
    live_returns: list[float],
    *,
    annualization: int = 252,
) -> float:
    paired = list(zip(theoretical_returns, live_returns, strict=False))
    if not paired:
        return 0.0
    squared = [(live - theoretical) ** 2 for theoretical, live in paired]
    return math.sqrt(sum(squared) / len(squared)) * math.sqrt(annualization)


def tracking_error_divergence(
    theoretical_returns: list[float],
    live_returns: list[float],
    *,
    threshold: float = 0.05,
) -> DivergenceResult:
    value = tracking_error(theoretical_returns, live_returns)
    severity = "red" if value > threshold * 1.5 else "yellow" if value > threshold else "green"
    return DivergenceResult(
        metric_type="tracking_error",
        backtest_value=0.0,
        live_value=value,
        tracking_error=value,
        threshold=threshold,
        severity=severity,
        reason=f"Tracking error {value:.4f} versus threshold {threshold:.4f}.",
        details={"sample_size": min(len(theoretical_returns), len(live_returns))},
    )


def sharpe_divergence(
    *,
    backtest_sharpe: float,
    backtest_sharpe_std: float,
    live_sharpe: float,
    live_sample_size: int,
    confidence: float = 0.95,
) -> DivergenceResult:
    z_value = 1.96 if confidence == 0.95 else 1.96
    half_width = z_value * backtest_sharpe_std / math.sqrt(max(1, live_sample_size))
    lower = backtest_sharpe - half_width
    upper = backtest_sharpe + half_width
    outside = live_sharpe < lower or live_sharpe > upper
    severity = "red" if outside else "green"
    return DivergenceResult(
        metric_type="sharpe_deviation",
        backtest_value=backtest_sharpe,
        live_value=live_sharpe,
        tracking_error=None,
        threshold=half_width,
        severity=severity,
        reason=(
            f"Live Sharpe {live_sharpe:.3f} is "
            f"{'outside' if outside else 'inside'} {confidence:.0%} backtest interval "
            f"[{lower:.3f}, {upper:.3f}]."
        ),
        details={
            "lower": lower,
            "upper": upper,
            "confidence": confidence,
            "live_sample_size": live_sample_size,
        },
    )


def algorithm_drift_divergence(
    *,
    original_metric: float,
    rerun_metric: float,
    threshold_pct: float = 0.05,
) -> DivergenceResult:
    denominator = max(abs(original_metric), 1e-9)
    drift_pct = abs(rerun_metric - original_metric) / denominator
    severity = "red" if drift_pct > threshold_pct else "green"
    return DivergenceResult(
        metric_type="algorithm_drift",
        backtest_value=original_metric,
        live_value=rerun_metric,
        tracking_error=None,
        threshold=threshold_pct,
        severity=severity,
        reason=f"Algorithm rerun drift {drift_pct:.2%} versus threshold {threshold_pct:.2%}.",
        details={"drift_pct": drift_pct},
    )


async def record_live_divergence(
    session: AsyncSession,
    *,
    strategy_hash: str,
    result: DivergenceResult,
    computed_at: datetime | None = None,
) -> LiveDivergenceMetric:
    effective_at = computed_at or datetime.now(timezone.utc)
    row = LiveDivergenceMetric(
        strategy_hash=strategy_hash,
        metric_type=result.metric_type,
        backtest_value=result.backtest_value,
        live_value=result.live_value,
        tracking_error=result.tracking_error,
        threshold=result.threshold,
        severity=result.severity,
        details=result.details,
        reason=result.reason,
        computed_at=effective_at,
    )
    session.add(row)
    if result.triggered:
        session.add(
            ChangeReviewQueue(
                source="backtest_live_divergence",
                target_table="strategy_runs",
                target_key=strategy_hash,
                proposed_change={
                    "action": "review_strategy_decay",
                    "metric": result.to_dict(),
                },
                reason=result.reason,
            )
        )
    await session.flush()
    return row
