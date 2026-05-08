from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.positions import publish_position_changed
from app.core.database import get_db
from app.models.position import Position
from app.models.recommendation import Recommendation
from app.schemas.common import PositionRead, RecommendationAdoptRequest, RecommendationCreate, RecommendationRead

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    status_filter: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Recommendation]:
    statement = select(Recommendation).order_by(Recommendation.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Recommendation.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


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
