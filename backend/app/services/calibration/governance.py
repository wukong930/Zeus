"""Apply an approved signal-calibration review to production.

Reconstructs the ``CalibrationProposal`` from the review's ``proposed_change``
and runs the guarded ``apply_signal_calibration_change`` (with the verified
approval) — connecting the previously-dead calibration governance loop.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.services.calibration.updater import CalibrationProposal, apply_signal_calibration_change
from app.services.governance.appliers import register_change_applier

CALIBRATION_REVIEW_SOURCE = "calibration"


async def apply_calibration_review(
    session: AsyncSession, row: ChangeReviewQueue, decided_by: str | None
) -> dict[str, Any]:
    payload = dict(row.proposed_change or {})
    try:
        proposal = CalibrationProposal(
            **{field.name: payload[field.name] for field in fields(CalibrationProposal)}
        )
    except (KeyError, TypeError):
        return {"applied": False, "production_effect": "none", "reason": "incomplete calibration proposal"}

    # Approval is enforced structurally — this applier only runs on an approved
    # review (via the applier registry) — not by a passable human_approved flag.
    calibration = await apply_signal_calibration_change(session, proposal)
    return {
        "applied": True,
        "production_effect": "calibration_applied",
        "target_key": proposal.target_key,
        "calibration_id": str(calibration.id),
        "decided_by": decided_by,
    }


def register_calibration_applier() -> None:
    register_change_applier(CALIBRATION_REVIEW_SOURCE, apply_calibration_review)
