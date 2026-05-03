from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import publish
from app.models.position import Position
from app.schemas.common import (
    PositionCloseRequest,
    PositionCreate,
    PositionMinimalCreate,
    PositionRead,
    PositionResizeRequest,
)

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
    await publish_position_changed(session, row, action="opened")
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/minimal", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
async def create_minimal_position(
    payload: PositionMinimalCreate,
    session: AsyncSession = Depends(get_db),
) -> Position:
    row = Position(
        recommendation_id=payload.recommendation_id,
        strategy_name=payload.strategy_name or f"{payload.symbol.upper()} manual position",
        legs=[
            {
                "asset": payload.symbol.upper(),
                "direction": payload.direction,
                "lots": payload.lots,
                "entry_price": payload.avg_entry_price,
                "current_price": payload.avg_entry_price,
            }
        ],
        opened_at=payload.opened_at,
        entry_spread=payload.avg_entry_price,
        current_spread=payload.avg_entry_price,
        spread_unit="price",
        unrealized_pnl=0,
        total_margin_used=payload.total_margin_used,
        exit_condition="manual_close",
        target_z_score=0,
        current_z_score=0,
        half_life_days=0,
        days_held=0,
        status="open",
        manual_entry=True,
        avg_entry_price=payload.avg_entry_price,
        monitoring_priority=5,
        data_mode="position_aware",
    )
    session.add(row)
    await session.commit()
    await publish_position_changed(session, row, action="opened")
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{position_id}", response_model=PositionRead)
async def get_position(position_id: UUID, session: AsyncSession = Depends(get_db)) -> Position:
    row = await session.get(Position, position_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return row


@router.post("/{position_id}/close", response_model=PositionRead)
async def close_position(
    position_id: UUID,
    payload: PositionCloseRequest,
    session: AsyncSession = Depends(get_db),
) -> Position:
    row = await require_position(session, position_id)
    closed_at = payload.closed_at or datetime.now(timezone.utc)
    row.status = "closed"
    row.closed_at = closed_at
    row.current_spread = payload.actual_exit if payload.actual_exit is not None else row.current_spread
    row.realized_pnl = payload.realized_pnl if payload.realized_pnl is not None else row.realized_pnl
    row.exit_condition = payload.actual_exit_reason
    row.last_updated_at = closed_at
    await session.commit()
    await publish_position_changed(session, row, action="closed")
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/{position_id}/add", response_model=PositionRead)
async def add_position_size(
    position_id: UUID,
    payload: PositionResizeRequest,
    session: AsyncSession = Depends(get_db),
) -> Position:
    row = await require_position(session, position_id)
    delta = payload.lots or 1
    row.legs = resize_legs(row.legs, delta=delta)
    row.last_updated_at = datetime.now(timezone.utc)
    await session.commit()
    await publish_position_changed(session, row, action="added", details={"lots": delta})
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/{position_id}/reduce", response_model=PositionRead)
async def reduce_position_size(
    position_id: UUID,
    payload: PositionResizeRequest,
    session: AsyncSession = Depends(get_db),
) -> Position:
    row = await require_position(session, position_id)
    row.legs = resize_legs(row.legs, fraction=payload.fraction or 0.5, reduce=True)
    row.last_updated_at = datetime.now(timezone.utc)
    await session.commit()
    await publish_position_changed(
        session,
        row,
        action="reduced",
        details={"fraction": payload.fraction or 0.5},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def require_position(session: AsyncSession, position_id: UUID) -> Position:
    row = await session.get(Position, position_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return row


async def publish_position_changed(
    session: AsyncSession,
    position: Position,
    *,
    action: str,
    details: dict | None = None,
) -> None:
    await publish(
        "position.changed",
        {
            "position_id": str(position.id),
            "action": action,
            "status": position.status,
            "recommendation_id": str(position.recommendation_id) if position.recommendation_id else None,
            "symbols": [
                str(leg.get("asset") or leg.get("symbol"))
                for leg in position.legs or []
                if isinstance(leg, dict)
            ],
            "details": details or {},
        },
        source="positions-api",
        session=session,
    )


def resize_legs(
    legs: list,
    *,
    delta: float | None = None,
    fraction: float | None = None,
    reduce: bool = False,
) -> list:
    resized: list = []
    for leg in legs or []:
        if not isinstance(leg, dict):
            resized.append(leg)
            continue
        row = dict(leg)
        current = float(row.get("lots") or row.get("size") or row.get("quantity") or 0)
        if reduce:
            next_value = max(0.0, current * (1 - float(fraction or 0.5)))
        else:
            next_value = current + float(delta or 0)
        if "lots" in row:
            row["lots"] = next_value
        elif "size" in row:
            row["size"] = next_value
        elif "quantity" in row:
            row["quantity"] = next_value
        else:
            row["lots"] = next_value
        resized.append(row)
    return resized
