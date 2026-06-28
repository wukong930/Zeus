"""Governance promotion of the cross-sectional forecast signal.

A shadow forecast signal (signal + model_version) is proposed for promotion,
reviewed, and — on approval — promoted to authoritative. The approval applier's
concrete production write is a fresh ``decision_grade=True`` forecast, and the
approved review row is the durable 'this version is authoritative' marker that
``is_signal_promoted`` checks (so future scheduled emissions are authoritative
too). Nothing becomes authoritative without a genuine governance approval.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.services.governance.appliers import register_change_applier
from app.services.governance.review_queue import enqueue_review
from app.services.prediction.cross_sectional import generate_cross_sectional_forecast

FORECAST_PROMOTION_SOURCE = "forecast_promotion"
FORECAST_PROMOTION_TABLE = "forecast_records"


def promotion_key(signal: str, model_version: str) -> str:
    return f"{signal}:{model_version}"


async def propose_forecast_promotion(
    session: AsyncSession,
    *,
    signal: str,
    model_version: str,
    evidence: dict[str, Any] | None = None,
) -> ChangeReviewQueue:
    return await enqueue_review(
        session,
        source=FORECAST_PROMOTION_SOURCE,
        target_table=FORECAST_PROMOTION_TABLE,
        target_key=promotion_key(signal, model_version),
        proposed_change={
            "signal": signal,
            "model_version": model_version,
            "evidence": evidence or {},
        },
        reason="Promote shadow forecast signal to authoritative.",
    )


async def is_signal_promoted(session: AsyncSession, *, signal: str, model_version: str) -> bool:
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
    return row is not None


async def apply_forecast_promotion(
    session: AsyncSession, row: ChangeReviewQueue, decided_by: str | None
) -> dict[str, Any]:
    payload = dict(row.proposed_change or {})
    signal = payload.get("signal")
    model_version = payload.get("model_version")
    if not signal or not model_version:
        return {"applied": False, "production_effect": "none", "reason": "missing signal/model_version"}

    # concrete production write: the first authoritative forecast of this version
    forecast = await generate_cross_sectional_forecast(
        session, as_of=datetime.now(UTC), decision_grade=True
    )
    return {
        "applied": True,
        "production_effect": "forecast_promoted",
        "signal": signal,
        "model_version": model_version,
        "authoritative_forecast_id": str(forecast.id),
        "decided_by": decided_by,
    }


def register_forecast_applier() -> None:
    register_change_applier(FORECAST_PROMOTION_SOURCE, apply_forecast_promotion)
