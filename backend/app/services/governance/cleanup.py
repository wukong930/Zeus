from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.change_review_queue import ChangeReviewQueue
from app.models.event_intelligence import (
    EventImpactLink,
    EventIntelligenceAuditLog,
    EventIntelligenceItem,
)
from app.models.recommendation import Recommendation
from app.services.event_intelligence.governance import event_intelligence_review_reasons
from app.services.governance.triage import triage_event_intelligence


@dataclass(frozen=True)
class ReviewLoadCleanupResult:
    expired_alerts: int
    scanned_alerts: int
    expired_recommendations: int
    scanned_recommendations: int
    event_reviews_scanned: int
    event_reviews_shadowed: int
    event_reviews_evidence_only: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            **asdict(self),
            "status": "completed",
        }


async def run_review_load_cleanup(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    limit: int = 1000,
) -> ReviewLoadCleanupResult:
    effective_as_of = as_of or datetime.now(UTC)
    rows = list(
        (
            await session.scalars(
                select(Alert)
                .where(
                    Alert.expires_at.is_not(None),
                    Alert.expires_at <= effective_as_of,
                    Alert.status.in_(("active", "pending")),
                )
                .order_by(Alert.expires_at.asc())
                .limit(limit)
            )
        ).all()
    )
    expired = 0
    for row in rows:
        if expire_alert_review_load(row, as_of=effective_as_of):
            expired += 1
    recommendation_rows = list(
        (
            await session.scalars(
                select(Recommendation)
                .where(
                    Recommendation.expires_at <= effective_as_of,
                    Recommendation.status.in_(("pending", "pending_review")),
                )
                .order_by(Recommendation.expires_at.asc())
                .limit(limit)
            )
        ).all()
    )
    expired_recommendations = 0
    for row in recommendation_rows:
        if expire_recommendation_review_load(row, as_of=effective_as_of):
            expired_recommendations += 1
    event_review_result = await triage_existing_event_reviews(session, as_of=effective_as_of)
    await session.flush()
    return ReviewLoadCleanupResult(
        expired_alerts=expired,
        scanned_alerts=len(rows),
        expired_recommendations=expired_recommendations,
        scanned_recommendations=len(recommendation_rows),
        event_reviews_scanned=event_review_result.event_reviews_scanned,
        event_reviews_shadowed=event_review_result.event_reviews_shadowed,
        event_reviews_evidence_only=event_review_result.event_reviews_evidence_only,
    )


def expire_alert_review_load(alert: Alert, *, as_of: datetime) -> bool:
    if alert.expires_at is None or alert.expires_at > as_of:
        return False
    if alert.status not in {"active", "pending"}:
        return False

    required_human = bool(alert.human_action_required)
    alert.human_action_required = False
    alert.human_action_deadline = None
    alert.status = "expired"
    alert.invalidation_reason = (
        "Expired before human review; removed from attention queue."
        if required_human
        else "Expired before execution; removed from active signal set."
    )
    return True


def expire_recommendation_review_load(recommendation: Recommendation, *, as_of: datetime) -> bool:
    if recommendation.expires_at > as_of:
        return False
    if recommendation.status not in {"pending", "pending_review"}:
        return False

    previous_status = recommendation.status
    recommendation.status = "expired"
    recommendation.ignored_reason = "Recommendation expired before adoption or review."
    summary = dict(recommendation.backtest_summary or {})
    summary["expired_at"] = as_of.isoformat()
    summary["previous_status"] = previous_status
    summary["review_required"] = False
    recommendation.backtest_summary = summary
    return True


@dataclass(frozen=True)
class EventReviewTriageCleanupResult:
    event_reviews_scanned: int
    event_reviews_shadowed: int
    event_reviews_evidence_only: int


async def triage_existing_event_reviews(
    session: AsyncSession,
    *,
    as_of: datetime,
    limit: int = 1000,
) -> EventReviewTriageCleanupResult:
    rows = list(
        (
            await session.scalars(
                select(ChangeReviewQueue)
                .where(
                    ChangeReviewQueue.source == "event_intelligence",
                    ChangeReviewQueue.target_table == "event_intelligence_items",
                    ChangeReviewQueue.status == "pending",
                )
                .order_by(ChangeReviewQueue.created_at.asc())
                .limit(limit)
            )
        ).all()
    )
    shadowed = 0
    evidence_only = 0
    for row in rows:
        result = await triage_existing_event_review(session, row, as_of=as_of)
        if result == "shadow_review":
            shadowed += 1
        elif result == "evidence_only":
            evidence_only += 1
    return EventReviewTriageCleanupResult(
        event_reviews_scanned=len(rows),
        event_reviews_shadowed=shadowed,
        event_reviews_evidence_only=evidence_only,
    )


async def triage_existing_event_review(
    session: AsyncSession,
    row: ChangeReviewQueue,
    *,
    as_of: datetime,
) -> str | None:
    try:
        event_item_id = UUID(row.target_key)
    except ValueError:
        return None
    event_item = await session.get(EventIntelligenceItem, event_item_id)
    if event_item is None:
        return None
    links = list(
        (
            await session.scalars(
                select(EventImpactLink)
                .where(EventImpactLink.event_item_id == event_item.id)
                .order_by(EventImpactLink.impact_score.desc())
            )
        ).all()
    )
    reasons = event_intelligence_review_reasons(event_item, links)
    triage = triage_event_intelligence(
        source_type=event_item.source_type,
        impact_score=event_item.impact_score,
        confidence=event_item.confidence,
        source_reliability=event_item.source_reliability,
        freshness_score=event_item.freshness_score,
        review_reasons=reasons,
        link_count=len(links),
        max_link_impact=max((link.impact_score for link in links), default=0.0),
        manual_operator_action=False,
    )
    proposed_change = dict(row.proposed_change or {})
    proposed_change["review_triage"] = triage.to_payload()
    row.proposed_change = proposed_change
    if triage.queue_status == "pending":
        return None
    row.status = triage.queue_status or "reviewed"
    row.reviewed_by = "review-triage"
    row.reviewed_at = as_of
    session.add(
        EventIntelligenceAuditLog(
            event_item_id=event_item.id,
            action=(
                "review.triage_backfilled_shadow"
                if triage.queue_status == "shadow_review"
                else "review.triage_backfilled_evidence_only"
            ),
            actor="review-triage",
            before_status=event_item.status,
            after_status=event_item.status,
            note="Existing pending review was reclassified by attention triage.",
            payload={
                "review_queue_id": str(row.id),
                "review_triage": triage.to_payload(),
                "production_effect": "none",
            },
        )
    )
    return triage.queue_status or "evidence_only"
