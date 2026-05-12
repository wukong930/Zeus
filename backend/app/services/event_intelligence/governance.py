from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_intelligence import (
    EventImpactLink,
    EventIntelligenceAuditLog,
    EventIntelligenceItem,
)

DECISION_STATUS: dict[str, str] = {
    "confirm": "confirmed",
    "reject": "rejected",
    "request_review": "human_review",
    "shadow_review": "shadow_review",
}


async def record_event_intelligence_audit(
    session: AsyncSession,
    *,
    event_item_id: UUID,
    action: str,
    actor: str | None = None,
    before_status: str | None = None,
    after_status: str | None = None,
    payload: dict[str, Any] | None = None,
    note: str | None = None,
) -> EventIntelligenceAuditLog:
    row = EventIntelligenceAuditLog(
        event_item_id=event_item_id,
        action=action,
        actor=actor,
        before_status=before_status,
        after_status=after_status,
        note=note,
        payload=payload or {},
    )
    session.add(row)
    await session.flush()
    return row


async def apply_event_intelligence_decision(
    session: AsyncSession,
    event_item_id: UUID,
    *,
    decision: str,
    decided_by: str | None = None,
    note: str | None = None,
    confidence_override: float | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[EventIntelligenceItem, EventIntelligenceAuditLog]:
    event_item = await session.get(EventIntelligenceItem, event_item_id)
    if event_item is None:
        raise ValueError("event intelligence item not found")

    after_status = DECISION_STATUS.get(decision)
    if after_status is None:
        raise ValueError("unsupported event intelligence decision")

    before_status = event_item.status
    before_confidence = event_item.confidence
    event_item.status = after_status
    if decision == "confirm":
        event_item.requires_manual_confirmation = False
    elif decision in {"reject", "request_review"}:
        event_item.requires_manual_confirmation = decision == "request_review"
    if confidence_override is not None:
        event_item.confidence = confidence_override
        event_item.impact_score = round(max(event_item.impact_score, confidence_override * 100), 2)

    await session.execute(
        update(EventImpactLink)
        .where(EventImpactLink.event_item_id == event_item.id)
        .values(status=after_status)
    )
    audit = await record_event_intelligence_audit(
        session,
        event_item_id=event_item.id,
        action=f"decision.{decision}",
        actor=decided_by,
        before_status=before_status,
        after_status=after_status,
        note=note,
        payload={
            "decision": decision,
            "confidence_override": confidence_override,
            "before_confidence": before_confidence,
            "symbols": list(event_item.symbols),
            "source_type": event_item.source_type,
            **(payload or {}),
        },
    )
    return event_item, audit
