from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Float, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.change_review_queue import ChangeReviewQueue
from app.schemas.governance import (
    ChangeReviewDecisionCreate,
    ChangeReviewRead,
    GOVERNANCE_REVIEW_STATUS_PATTERN,
    GOVERNANCE_REVIEW_TRIAGE_TIER_PATTERN,
)
from app.services.event_intelligence.governance import (
    EVENT_INTELLIGENCE_REVIEW_SOURCE,
    EVENT_INTELLIGENCE_REVIEW_TABLE,
    apply_event_intelligence_decision,
)
from app.services.governance.appliers import apply_approved_change

router = APIRouter(prefix="/api/governance", tags=["governance"])

DECISION_TO_STATUS = {
    "approve": "approved",
    "reject": "rejected",
    "mark_reviewed": "reviewed",
    "shadow_review": "shadow_review",
}

EVENT_INTELLIGENCE_DECISION_MAP = {
    "approve": "confirm",
    "reject": "reject",
    "shadow_review": "shadow_review",
}


@router.get("/reviews", response_model=list[ChangeReviewRead])
async def list_change_reviews(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=GOVERNANCE_REVIEW_STATUS_PATTERN,
    ),
    source: str | None = Query(default=None, min_length=1, max_length=40),
    target_table: str | None = Query(default=None, min_length=1, max_length=80),
    triage_tier: str | None = Query(
        default=None,
        pattern=GOVERNANCE_REVIEW_TRIAGE_TIER_PATTERN,
    ),
    min_attention_score: float | None = Query(default=None, ge=0, le=100),
    requires_human_attention: bool | None = None,
    before: datetime | None = Query(default=None),
    before_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[ChangeReviewQueue]:
    statement = change_reviews_statement(
        status_filter=status_filter,
        source=source,
        target_table=target_table,
        triage_tier=triage_tier,
        min_attention_score=min_attention_score,
        requires_human_attention=requires_human_attention,
        before=before,
        before_id=before_id,
        limit=limit,
    )
    return list((await session.scalars(statement)).all())


def change_reviews_statement(
    *,
    status_filter: str | None,
    source: str | None,
    target_table: str | None,
    triage_tier: str | None,
    min_attention_score: float | None,
    requires_human_attention: bool | None,
    limit: int,
    before: datetime | None = None,
    before_id: UUID | None = None,
):
    statement = select(ChangeReviewQueue).order_by(
        ChangeReviewQueue.created_at.desc(),
        ChangeReviewQueue.id.desc(),
    )
    if status_filter is not None:
        statement = statement.where(ChangeReviewQueue.status == status_filter)
    if source is not None:
        statement = statement.where(ChangeReviewQueue.source == source)
    if target_table is not None:
        statement = statement.where(ChangeReviewQueue.target_table == target_table)
    if triage_tier is not None:
        statement = statement.where(
            ChangeReviewQueue.proposed_change["review_triage"]["tier"].as_string()
            == triage_tier
        )
    if min_attention_score is not None:
        attention_score = cast(
            ChangeReviewQueue.proposed_change["review_triage"]["attention_score"].as_string(),
            Float,
        )
        statement = statement.where(attention_score >= min_attention_score)
    if requires_human_attention is not None:
        statement = statement.where(
            ChangeReviewQueue.proposed_change["review_triage"][
                "requires_human_attention"
            ].as_boolean()
            .is_(requires_human_attention)
        )
    if before is not None:
        if before_id is not None:
            statement = statement.where(
                or_(
                    ChangeReviewQueue.created_at < before,
                    and_(
                        ChangeReviewQueue.created_at == before,
                        ChangeReviewQueue.id < before_id,
                    ),
                )
            )
        else:
            statement = statement.where(ChangeReviewQueue.created_at < before)
    return statement.limit(limit)


@router.get("/reviews/{review_id}", response_model=ChangeReviewRead)
async def get_change_review(
    review_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ChangeReviewQueue:
    row = await session.get(ChangeReviewQueue, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Change review not found")
    return row


@router.post("/reviews/{review_id}/decision", response_model=ChangeReviewRead)
async def decide_change_review(
    review_id: UUID,
    payload: ChangeReviewDecisionCreate,
    session: AsyncSession = Depends(get_db),
) -> ChangeReviewQueue:
    row = await session.get(ChangeReviewQueue, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Change review not found")
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change review has already been decided",
        )

    now = datetime.now(UTC)
    if _is_event_intelligence_review(row) and payload.decision in EVENT_INTELLIGENCE_DECISION_MAP:
        try:
            await apply_event_intelligence_decision(
                session,
                UUID(row.target_key),
                decision=EVENT_INTELLIGENCE_DECISION_MAP[payload.decision],
                decided_by=payload.reviewed_by,
                note=payload.note,
            )
        except ValueError as exc:
            if "not found" in str(exc):
                raise HTTPException(
                    status_code=404,
                    detail="Linked event intelligence item not found",
                ) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    applied: dict[str, Any] | None = None
    if not _is_event_intelligence_review(row) or payload.decision not in EVENT_INTELLIGENCE_DECISION_MAP:
        row.status = DECISION_TO_STATUS[payload.decision]
        row.reviewed_by = payload.reviewed_by
        row.reviewed_at = now
        # approval -> apply: dispatch the production write to the registered applier
        if row.status == "approved":
            applied = await apply_approved_change(session, row, decided_by=payload.reviewed_by)

    _append_review_decision(row, payload, now, applied=applied)
    await session.commit()
    await session.refresh(row)
    return row


def _is_event_intelligence_review(row: ChangeReviewQueue) -> bool:
    if row.source != EVENT_INTELLIGENCE_REVIEW_SOURCE:
        return False
    if row.target_table != EVENT_INTELLIGENCE_REVIEW_TABLE:
        return False
    try:
        UUID(row.target_key)
    except ValueError:
        return False
    return True


def _append_review_decision(
    row: ChangeReviewQueue,
    payload: ChangeReviewDecisionCreate,
    decided_at: datetime,
    *,
    applied: dict[str, Any] | None = None,
) -> None:
    proposed_change: dict[str, Any] = dict(row.proposed_change or {})
    proposed_change["review_decision"] = {
        "decision": payload.decision,
        "status": row.status,
        "reviewed_by": payload.reviewed_by,
        "reviewed_at": (row.reviewed_at or decided_at).isoformat(),
        "note": payload.note,
        "production_effect": (applied or {}).get("production_effect", "none"),
        "applied": applied,
    }
    row.proposed_change = proposed_change
