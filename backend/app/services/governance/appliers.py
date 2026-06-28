"""Approved-change applier registry — the 'approval → apply' step.

Closes the governance loop the original review flagged as dead: previously an
approved ChangeReviewQueue row only flipped status and recorded a hardcoded
``production_effect: "none"`` — nothing was ever applied. Now an approval is
dispatched, by ``source``, to a registered applier that performs the actual,
guarded production write and returns what it did.

Appliers are the ONLY place a production write happens off the back of a review,
and they only run from ``decide_change_review`` after a genuine approval — so a
forged ``human_approved`` kwarg can no longer reach production on its own.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue

# (session, approved_row, decided_by) -> production_effect payload
ChangeApplier = Callable[[AsyncSession, ChangeReviewQueue, str | None], Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, ChangeApplier] = {}
_registered = False

NO_EFFECT = {"applied": False, "production_effect": "none"}


def register_change_applier(source: str, applier: ChangeApplier) -> None:
    _REGISTRY[source] = applier


def _ensure_registered() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    # imported lazily to avoid import cycles (these modules import this one)
    from app.services.calibration.governance import register_calibration_applier
    from app.services.prediction.governance import register_forecast_applier

    register_calibration_applier()
    register_forecast_applier()


async def apply_approved_change(
    session: AsyncSession,
    row: ChangeReviewQueue,
    *,
    decided_by: str | None = None,
) -> dict[str, Any]:
    _ensure_registered()
    applier = _REGISTRY.get(row.source)
    if applier is None:
        return {**NO_EFFECT, "reason": f"no applier registered for source '{row.source}'"}
    return await applier(session, row, decided_by)
