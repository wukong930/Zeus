from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.position import Position
from app.schemas.common import PositionCreate, PositionRead

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("", response_model=list[PositionRead])
async def list_positions(
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Position]:
    statement = select(Position).order_by(Position.opened_at.desc())
    if status_filter is not None:
        statement = statement.where(Position.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
async def create_position(payload: PositionCreate, session: AsyncSession = Depends(get_db)) -> Position:
    row = Position(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{position_id}", response_model=PositionRead)
async def get_position(position_id: UUID, session: AsyncSession = Depends(get_db)) -> Position:
    row = await session.get(Position, position_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return row
