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
EVENT_INTELLIGENCE_MAX_AGGREGATE_VALUES = 40


IMPACT_LINK_UPDATE_FIELDS = (
    "symbol",
    "region_id",
    "mechanism",
    "direction",
    "confidence",
    "impact_score",
    "horizon",
    "rationale",
    "evidence",
    "counterevidence",
)


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


async def update_event_impact_link(
    session: AsyncSession,
    link_id: UUID,
    *,
    edited_by: str | None = None,
    note: str | None = None,
    changes: dict[str, Any],
) -> tuple[EventIntelligenceItem, EventImpactLink, EventIntelligenceAuditLog]:
    link = await session.get(EventImpactLink, link_id)
    if link is None:
        raise ValueError("event impact link not found")
    event_item = await session.get(EventIntelligenceItem, link.event_item_id)
    if event_item is None:
        raise ValueError("event intelligence item not found")

    before_link = _impact_link_snapshot(link)
    applied_changes = {
        field: changes[field]
        for field in IMPACT_LINK_UPDATE_FIELDS
        if field in changes
    }
    if not applied_changes:
        raise ValueError("no impact link changes supplied")

    before_status = event_item.status
    for field, value in applied_changes.items():
        setattr(link, field, value)

    link.status = "human_review"
    event_item.status = "human_review"
    event_item.requires_manual_confirmation = True
    await session.flush()

    links = await _event_links(session, event_item.id)
    _recompute_event_scope(event_item, links)
    audit = await record_event_intelligence_audit(
        session,
        event_item_id=event_item.id,
        action="impact_link.updated",
        actor=edited_by,
        before_status=before_status,
        after_status=event_item.status,
        note=note,
        payload={
            "impact_link_id": str(link.id),
            "before": before_link,
            "after": _impact_link_snapshot(link),
            "changed_fields": list(applied_changes.keys()),
            "production_effect": "none",
        },
    )
    await enqueue_event_intelligence_review(session, event_item, links, actor=edited_by or "operator")
    await record_event_intelligence_review_learning(
        session,
        event_item=event_item,
        audit_log=audit,
    )
    return event_item, link, audit


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


async def _event_links(session: AsyncSession, event_item_id: UUID) -> list[EventImpactLink]:
    rows = await session.scalars(
        select(EventImpactLink)
        .where(EventImpactLink.event_item_id == event_item_id)
        .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
    )
    return list(rows.all())


def _recompute_event_scope(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink],
) -> None:
    event_item.symbols = _unique_limited(link.symbol for link in links if link.symbol)
    event_item.regions = _unique_limited(link.region_id for link in links if link.region_id)
    event_item.mechanisms = _unique_limited(link.mechanism for link in links if link.mechanism)
    event_item.impact_score = round(max((link.impact_score for link in links), default=0), 2)
    event_item.confidence = round(max((link.confidence for link in links), default=0), 4)
    event_item.evidence = _unique_limited(
        [*event_item.evidence, *(item for link in links for item in link.evidence)]
    )
    event_item.counterevidence = _unique_limited(
        [*event_item.counterevidence, *(item for link in links for item in link.counterevidence)]
    )


def _unique_limited(values) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
        if len(unique) >= EVENT_INTELLIGENCE_MAX_AGGREGATE_VALUES:
            break
    return unique


def _impact_link_snapshot(link: EventImpactLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "symbol": link.symbol,
        "region_id": link.region_id,
        "mechanism": link.mechanism,
        "direction": link.direction,
        "confidence": link.confidence,
        "impact_score": link.impact_score,
        "horizon": link.horizon,
        "rationale": link.rationale,
        "evidence": list(link.evidence),
        "counterevidence": list(link.counterevidence),
        "status": link.status,
    }
