from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.models.event_intelligence import (
    EventImpactLink,
    EventIntelligenceAuditLog,
    EventIntelligenceItem,
)
from app.models.vector_chunks import VectorChunk
from app.services.governance.review_queue import enqueue_review

DECISION_STATUS: dict[str, str] = {
    "confirm": "confirmed",
    "reject": "rejected",
    "request_review": "human_review",
    "shadow_review": "shadow_review",
}
EVENT_INTELLIGENCE_REVIEW_SOURCE = "event_intelligence"
EVENT_INTELLIGENCE_REVIEW_TABLE = "event_intelligence_items"
HIGH_IMPACT_REVIEW_THRESHOLD = 70
LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.65
LOW_SOURCE_RELIABILITY_THRESHOLD = 0.6


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


def event_intelligence_review_reasons(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink] | tuple[EventImpactLink, ...] = (),
) -> list[str]:
    reasons: list[str] = []
    source_count = _payload_int(event_item.source_payload, "source_count")
    verification_status = str(event_item.source_payload.get("verification_status") or "")
    single_source = source_count <= 1 or verification_status == "single_source"
    low_confidence = event_item.confidence < LOW_CONFIDENCE_REVIEW_THRESHOLD
    low_reliability = event_item.source_reliability < LOW_SOURCE_RELIABILITY_THRESHOLD
    high_impact = event_item.impact_score >= HIGH_IMPACT_REVIEW_THRESHOLD

    if event_item.requires_manual_confirmation or event_item.status == "human_review":
        reasons.append("manual_confirmation_required")
    if single_source:
        reasons.append("single_source")
    if low_confidence:
        reasons.append("low_confidence")
    if low_reliability:
        reasons.append("low_source_reliability")
    if high_impact and (single_source or low_confidence or low_reliability):
        reasons.append("high_impact_uncertain_event")
    if any(link.status == "human_review" for link in links):
        reasons.append("impact_link_requires_review")
    return list(dict.fromkeys(reasons))


async def enqueue_event_intelligence_review(
    session: AsyncSession,
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink] | tuple[EventImpactLink, ...] = (),
    *,
    actor: str = "event_intelligence",
) -> ChangeReviewQueue | None:
    reasons = event_intelligence_review_reasons(event_item, links)
    if not reasons:
        return None

    existing = await _pending_review_for_event(session, event_item.id)
    if existing is not None:
        return existing

    review = await enqueue_review(
        session,
        source=EVENT_INTELLIGENCE_REVIEW_SOURCE,
        target_table=EVENT_INTELLIGENCE_REVIEW_TABLE,
        target_key=str(event_item.id),
        proposed_change=_review_payload(event_item, links, reasons),
        reason="Event intelligence result requires human governance before decision-grade use.",
    )
    await record_event_intelligence_audit(
        session,
        event_item_id=event_item.id,
        action="review.queued",
        actor=actor,
        before_status=event_item.status,
        after_status=event_item.status,
        note="Queued for human review; result remains shadow/review scoped.",
        payload={
            "review_queue_id": str(review.id),
            "review_reasons": reasons,
            "production_effect": "none",
        },
    )
    return review


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
    await mark_event_intelligence_review_decided(
        session,
        event_item_id=event_item.id,
        decision=decision,
        reviewed_by=decided_by,
    )
    await record_event_intelligence_review_learning(
        session,
        event_item=event_item,
        audit_log=audit,
    )
    return event_item, audit


async def mark_event_intelligence_review_decided(
    session: AsyncSession,
    *,
    event_item_id: UUID,
    decision: str,
    reviewed_by: str | None = None,
) -> ChangeReviewQueue | None:
    review = await _pending_review_for_event(session, event_item_id)
    if review is None:
        return None
    if decision == "request_review":
        return review
    review.status = {
        "confirm": "approved",
        "reject": "rejected",
        "shadow_review": "shadow_review",
    }.get(decision, "reviewed")
    review.reviewed_by = reviewed_by
    review.reviewed_at = datetime.now(UTC)
    return review


async def record_event_intelligence_review_learning(
    session: AsyncSession,
    *,
    event_item: EventIntelligenceItem,
    audit_log: EventIntelligenceAuditLog,
) -> VectorChunk:
    chunk = VectorChunk(
        chunk_type="event_intelligence_review",
        source_id=event_item.id,
        content_text="\n".join(
            item
            for item in (
                event_item.title,
                event_item.summary,
                f"Decision: {audit_log.action}",
                f"Status: {audit_log.before_status} -> {audit_log.after_status}",
                audit_log.note or "",
                "Symbols: " + ", ".join(event_item.symbols),
                "Mechanisms: " + ", ".join(event_item.mechanisms),
                "Evidence: " + "; ".join(event_item.evidence[:5]),
                "Counterevidence: " + "; ".join(event_item.counterevidence[:5]),
            )
            if item
        ),
        embedding=None,
        embedding_model=None,
        metadata_json={
            "source": EVENT_INTELLIGENCE_REVIEW_SOURCE,
            "audit_log_id": str(audit_log.id),
            "action": audit_log.action,
            "status": event_item.status,
            "symbols": list(event_item.symbols),
            "mechanisms": list(event_item.mechanisms),
            "production_effect": "none",
        },
        quality_status="human_reviewed",
    )
    session.add(chunk)
    await session.flush()
    return chunk


async def _pending_review_for_event(
    session: AsyncSession,
    event_item_id: UUID,
) -> ChangeReviewQueue | None:
    rows = await session.scalars(
        select(ChangeReviewQueue)
        .where(
            ChangeReviewQueue.source == EVENT_INTELLIGENCE_REVIEW_SOURCE,
            ChangeReviewQueue.target_table == EVENT_INTELLIGENCE_REVIEW_TABLE,
            ChangeReviewQueue.target_key == str(event_item_id),
            ChangeReviewQueue.status == "pending",
        )
        .limit(1)
    )
    return rows.first()


def _review_payload(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink] | tuple[EventImpactLink, ...],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "event_item_id": str(event_item.id),
        "source_type": event_item.source_type,
        "source_id": event_item.source_id,
        "title": event_item.title,
        "symbols": list(event_item.symbols),
        "mechanisms": list(event_item.mechanisms),
        "confidence": event_item.confidence,
        "impact_score": event_item.impact_score,
        "status": event_item.status,
        "requires_manual_confirmation": event_item.requires_manual_confirmation,
        "review_reasons": reasons,
        "link_count": len(links),
        "top_links": [
            {
                "id": str(link.id),
                "symbol": link.symbol,
                "mechanism": link.mechanism,
                "direction": link.direction,
                "confidence": link.confidence,
                "impact_score": link.impact_score,
                "status": link.status,
            }
            for link in sorted(links, key=lambda row: row.impact_score, reverse=True)[:5]
        ],
        "production_effect": "none",
    }


def _payload_int(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0
