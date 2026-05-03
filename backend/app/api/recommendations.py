from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.recommendation import Recommendation
from app.schemas.common import RecommendationCreate, RecommendationRead

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    status_filter: str | None = None,
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
