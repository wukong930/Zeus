from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.alert_agent import HumanDecision


async def record_human_decision(
    session: AsyncSession,
    *,
    alert_id: UUID | None,
    signal_track_id: UUID | None = None,
    decision: str,
    confidence_override: float | None = None,
    reasoning: str | None = None,
    decided_by: str | None = None,
    payload: dict[str, Any] | None = None,
) -> HumanDecision:
    row = HumanDecision(
        alert_id=alert_id,
        signal_track_id=signal_track_id,
        decision=decision,
        confidence_override=confidence_override,
        reasoning=reasoning,
        decided_by=decided_by,
        payload=payload or {},
    )
    session.add(row)
    if alert_id is not None:
        alert = await session.get(Alert, alert_id)
        if alert is not None:
            apply_decision_to_alert(alert, decision, confidence_override)
    await session.flush()
    return row


def apply_decision_to_alert(
    alert: Alert,
    decision: str,
    confidence_override: float | None,
) -> None:
    if confidence_override is not None:
        alert.confidence = max(0.0, min(1.0, confidence_override))
    alert.human_action_required = False
    alert.human_action_deadline = None
    if decision == "reject":
        alert.status = "dismissed"
    elif decision in {"approve", "modify"} and alert.status in {"pending", "suppressed"}:
        alert.status = "active"
