from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.positions import publish_position_changed
from app.core.database import get_db
from app.models.position import Position
from app.models.recommendation import Recommendation
from app.schemas.common import (
    PositionRead,
    RecommendationAdoptRequest,
    RecommendationCreate,
    RecommendationRead,
    RecommendationReviewRequest,
)
from app.services.alert_agent.human_decision import record_human_decision

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    status_filter: str | None = Query(default=None, max_length=20),
    before: datetime | None = Query(default=None),
    before_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Recommendation]:
    statement = _recommendations_statement(
        status_filter=status_filter,
        before=before,
        before_id=before_id,
        limit=limit,
    )
    return list((await session.scalars(statement)).all())


def _recommendations_statement(
    *,
    status_filter: str | None,
    before: datetime | None,
    limit: int,
    before_id: UUID | None = None,
):
    statement = select(Recommendation).order_by(
        Recommendation.created_at.desc(),
        Recommendation.id.desc(),
    )
    if status_filter is not None:
        statement = statement.where(Recommendation.status == status_filter)
    if before is not None:
        if before_id is not None:
            statement = statement.where(
                or_(
                    Recommendation.created_at < before,
                    and_(Recommendation.created_at == before, Recommendation.id < before_id),
                )
            )
        else:
            statement = statement.where(Recommendation.created_at < before)
    return statement.limit(limit)


@router.post("", response_model=RecommendationRead, status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    payload: RecommendationCreate,
    session: AsyncSession = Depends(get_db),
) -> Recommendation:
    row = Recommendation(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{recommendation_id}", response_model=RecommendationRead)
async def get_recommendation(
    recommendation_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Recommendation:
    row = await session.get(Recommendation, recommendation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return row


@router.post("/{recommendation_id}/review", response_model=RecommendationRead)
async def review_recommendation(
    recommendation_id: UUID,
    payload: RecommendationReviewRequest,
    session: AsyncSession = Depends(get_db),
) -> Recommendation:
    row = await apply_recommendation_review(
        session,
        recommendation_id,
        payload,
        as_of=datetime.now(timezone.utc),
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/{recommendation_id}/adopt", response_model=PositionRead)
async def adopt_recommendation(
    recommendation_id: UUID,
    payload: RecommendationAdoptRequest,
    session: AsyncSession = Depends(get_db),
) -> Position:
    now = datetime.now(timezone.utc)
    recommendation = await require_adoptable_recommendation(session, recommendation_id, as_of=now)
    opened_at = payload.opened_at or now
    actual_entry = payload.actual_entry or recommendation.entry_price or inferred_entry_price(recommendation)
    recommendation.status = "accepted"
    recommendation.actual_entry = actual_entry
    if recommendation.entry_price is None:
        recommendation.entry_price = actual_entry

    position = Position(
        strategy_id=recommendation.strategy_id,
        recommendation_id=recommendation.id,
        strategy_name=f"Recommendation {str(recommendation.id)[:8]}",
        legs=position_legs_from_recommendation(recommendation, lots=payload.lots, entry_price=actual_entry),
        opened_at=opened_at,
        entry_spread=actual_entry,
        current_spread=actual_entry,
        spread_unit="price",
        unrealized_pnl=0,
        total_margin_used=payload.total_margin_used or recommendation.margin_required,
        exit_condition="recommendation_exit",
        target_z_score=0,
        current_z_score=0,
        half_life_days=float(recommendation.max_holding_days or 0),
        days_held=0,
        status="open",
        manual_entry=False,
        avg_entry_price=actual_entry,
        monitoring_priority=10,
    )
    session.add(position)
    await session.commit()
    await publish_position_changed(session, position, action="adopted")
    await session.commit()
    await session.refresh(position)
    return position


async def apply_recommendation_review(
    session: AsyncSession,
    recommendation_id: UUID,
    payload: RecommendationReviewRequest,
    *,
    as_of: datetime | None = None,
) -> Recommendation:
    recommendation = await session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if recommendation.status != "pending_review":
        raise HTTPException(status_code=409, detail="Recommendation is not pending review")

    effective_at = _aware_utc(as_of or datetime.now(timezone.utc))
    if payload.decision == "approve" and _aware_utc(recommendation.expires_at) <= effective_at:
        raise HTTPException(status_code=409, detail="Recommendation has expired")

    if payload.decision == "approve":
        recommendation.status = "pending"
        recommendation.ignored_reason = None
    else:
        recommendation.status = "ignored"
        recommendation.ignored_reason = payload.reason or "Rejected during trade plan review."

    recommendation.backtest_summary = recommendation_review_summary(
        recommendation.backtest_summary,
        payload,
        reviewed_at=effective_at,
    )

    await record_human_decision(
        session,
        alert_id=recommendation.alert_id,
        decision=payload.decision,
        confidence_override=payload.confidence_override,
        reasoning=payload.reason,
        decided_by=payload.reviewed_by,
        payload={
            "recommendation_id": str(recommendation.id),
            "recommended_action": recommendation.recommended_action,
            "source": "trade_plan_review",
        },
    )
    await session.flush()
    return recommendation


def recommendation_review_summary(
    current: dict | None,
    payload: RecommendationReviewRequest,
    *,
    reviewed_at: datetime,
) -> dict:
    summary = dict(current or {})
    decision_payload = {
        "decision": payload.decision,
        "reviewed_by": payload.reviewed_by,
        "reason": payload.reason,
        "reviewed_at": reviewed_at.isoformat(),
    }
    history = summary.get("review_decisions")
    decisions = history if isinstance(history, list) else []
    summary["review_decision"] = decision_payload
    summary["review_decisions"] = [*decisions, decision_payload][-20:]
    if payload.decision == "approve":
        summary["review_required"] = False
        summary["review_reasons"] = []
    else:
        summary["review_required"] = True
        summary["review_reasons"] = [
            f"人工驳回：{payload.reason}" if payload.reason else "人工驳回交易计划"
        ]
    return summary


async def require_adoptable_recommendation(
    session: AsyncSession,
    recommendation_id: UUID,
    *,
    as_of: datetime | None = None,
) -> Recommendation:
    recommendation = await session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if recommendation.status != "pending":
        raise HTTPException(status_code=409, detail="Recommendation is not pending")
    effective_at = _aware_utc(as_of or datetime.now(timezone.utc))
    if _aware_utc(recommendation.expires_at) <= effective_at:
        raise HTTPException(status_code=409, detail="Recommendation has expired")
    return recommendation


def position_legs_from_recommendation(
    recommendation: Recommendation,
    *,
    lots: float,
    entry_price: float,
) -> list[dict]:
    legs = []
    for leg in recommendation.legs or []:
        if not isinstance(leg, dict):
            continue
        row = dict(leg)
        row.setdefault("lots", lots)
        row.setdefault("entry_price", entry_price)
        row.setdefault("current_price", entry_price)
        legs.append(row)
    return legs or [{"asset": "UNKNOWN", "direction": "long", "lots": lots, "entry_price": entry_price}]


def inferred_entry_price(recommendation: Recommendation) -> float:
    for leg in recommendation.legs or []:
        if isinstance(leg, dict):
            value = leg.get("entry_price") or leg.get("entryPrice") or leg.get("price")
            if value is not None:
                return float(value)
    return 0.0


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
