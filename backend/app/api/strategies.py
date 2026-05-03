from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.strategy import Strategy
from app.schemas.common import StrategyCreate, StrategyRead

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyRead])
async def list_strategies(
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Strategy]:
    statement = select(Strategy).order_by(Strategy.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Strategy.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=StrategyRead, status_code=status.HTTP_201_CREATED)
async def create_strategy(payload: StrategyCreate, session: AsyncSession = Depends(get_db)) -> Strategy:
    row = Strategy(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{strategy_id}", response_model=StrategyRead)
async def get_strategy(strategy_id: UUID, session: AsyncSession = Depends(get_db)) -> Strategy:
    row = await session.get(Strategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return row
