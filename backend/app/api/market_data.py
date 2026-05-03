from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.market_data import MarketData
from app.schemas.common import MarketDataCreate, MarketDataRead
from app.services.market_data.pit import get_market_data_pit

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("", response_model=list[MarketDataRead])
async def list_market_data(
    symbol: str,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_db),
) -> list[MarketData]:
    return await get_market_data_pit(
        session,
        symbol=symbol,
        as_of=as_of,
        start=start,
        end=end,
        limit=limit,
    )


@router.post("", response_model=MarketDataRead, status_code=status.HTTP_201_CREATED)
async def create_market_data(
    payload: MarketDataCreate,
    session: AsyncSession = Depends(get_db),
) -> MarketData:
    row = MarketData(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{market_data_id}", response_model=MarketDataRead)
async def get_market_data(
    market_data_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> MarketData:
    row = await session.get(MarketData, market_data_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Market data row not found")
    return row


@router.get("/symbols/{symbol}/latest", response_model=MarketDataRead)
async def get_latest_market_data(
    symbol: str,
    session: AsyncSession = Depends(get_db),
) -> MarketData:
    row = (
        await session.scalars(
            select(MarketData)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.timestamp.desc(), MarketData.vintage_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Market data row not found")
    return row
