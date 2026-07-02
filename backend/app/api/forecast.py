"""Read-only API for the cross-sectional forecast lifecycle (operator view).

Surfaces what an operator needs to SEE about the governed prediction signal — the
latest forecast (dollar-neutral target weights + provenance), the shadow track
record, the promotion status, and the live-divergence assessment. Mutations
(promotion / demotion) stay in the governance + scheduler flows; this router only
reads, so it can never move a signal to authoritative on its own.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.forecast import ForecastRecord
from app.services.prediction.cross_sectional import DEFAULT_LOOKBACK, MODEL_VERSION
from app.services.prediction.divergence import assess_divergence, live_performance
from app.services.prediction.governance import is_signal_promoted
from app.services.prediction.shadow import shadow_performance

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

DEFAULT_SIGNAL = f"xs_reversal_mom{DEFAULT_LOOKBACK}"


def _forecast_to_dict(row: ForecastRecord) -> dict[str, Any]:
    weights: dict[str, float] = row.target_weights or {}
    longs = sorted((sym for sym, weight in weights.items() if weight > 0))
    shorts = sorted((sym for sym, weight in weights.items() if weight < 0))
    return {
        "id": str(row.id),
        "as_of": row.as_of.isoformat(),
        "signal": row.signal,
        "model_version": row.model_version,
        "feature_hash": row.feature_hash,
        "decision_grade": row.decision_grade,
        "horizon_days": row.horizon_days,
        "universe_size": row.universe_size,
        "long": longs,  # long the losers (cross-sectional reversal)
        "short": shorts,  # short the winners
        "target_weights": weights,
        "realized_return": row.realized_return,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _latest_forecast(session: AsyncSession, signal: str) -> ForecastRecord | None:
    return (
        await session.scalars(
            select(ForecastRecord)
            .where(ForecastRecord.signal == signal)
            .order_by(ForecastRecord.as_of.desc(), ForecastRecord.id.desc())
            .limit(1)
        )
    ).first()


@router.get("/overview")
async def forecast_overview(
    signal: str = Query(default=DEFAULT_SIGNAL),
    model_version: str = Query(default=MODEL_VERSION),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    latest = await _latest_forecast(session, signal)
    promoted = await is_signal_promoted(session, signal=signal, model_version=model_version)
    performance = await shadow_performance(session, signal=signal)
    live = await live_performance(session, signal=signal)
    breached, reason = assess_divergence(live)
    return {
        "signal": signal,
        "model_version": model_version,
        "promoted": promoted,
        "status": "authoritative" if promoted else "shadow",
        "latest": _forecast_to_dict(latest) if latest is not None else None,
        "shadow_performance": performance.to_dict(),
        "live": {
            "periods": live.periods,
            "mean_return": round(live.mean_return, 6),
            "sharpe": round(live.sharpe, 4),
            "max_drawdown": round(live.max_drawdown, 4),
            "breached": breached,
            "reason": reason,
        },
    }


@router.get("/history")
async def forecast_history(
    signal: str = Query(default=DEFAULT_SIGNAL),
    limit: int = Query(default=30, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = list(
        (
            await session.scalars(
                select(ForecastRecord)
                .where(ForecastRecord.signal == signal)
                .order_by(ForecastRecord.as_of.desc(), ForecastRecord.id.desc())
                .limit(limit)
            )
        ).all()
    )
    return {"signal": signal, "records": [_forecast_to_dict(row) for row in rows]}
