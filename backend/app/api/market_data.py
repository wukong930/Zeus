from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.market_data import MarketData
from app.schemas.common import MarketDataCreate, MarketDataRead
from app.services.etl.writers import append_market_data
from app.services.market_data.pit import get_market_data_pit

router = APIRouter(prefix="/api/market-data", tags=["market-data"])
MAX_BATCH_SYMBOLS = 50


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
    row = (await append_market_data(session, [payload]))[0]
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/latest", response_model=list[MarketDataRead])
async def get_latest_market_data_batch(
    symbols: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db),
) -> list[MarketData]:
    return await latest_market_data_for_symbols(session, _parse_market_symbols(symbols))


@router.get("/recent", response_model=list[MarketDataRead])
async def get_recent_market_data_batch(
    symbols: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[MarketData]:
    return await recent_market_data_for_symbols(
        session,
        _parse_market_symbols(symbols),
        limit=limit,
    )


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
    rows = await latest_market_data_for_symbols(session, [symbol])
    if not rows:
        raise HTTPException(status_code=404, detail="Market data row not found")
    return rows[0]


async def latest_market_data_for_symbols(
    session: AsyncSession,
    symbols: list[str],
) -> list[MarketData]:
    requested_symbols = list(
        dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
    )
    if not requested_symbols:
        return []

    rows = list((await session.scalars(_latest_market_data_statement(requested_symbols))).all())
    rows_by_symbol = {row.symbol.upper(): row for row in rows}
    return [rows_by_symbol[symbol] for symbol in requested_symbols if symbol in rows_by_symbol]


async def recent_market_data_for_symbols(
    session: AsyncSession,
    symbols: list[str],
    *,
    limit: int,
) -> list[MarketData]:
    requested_symbols = list(
        dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
    )
    if not requested_symbols:
        return []

    return list(
        (await session.scalars(_recent_market_data_statement(requested_symbols, limit))).all()
    )


def _latest_market_data_statement(symbols: list[str]):
    ranked = (
        select(
            MarketData.id.label("id"),
            func.row_number()
            .over(
                partition_by=MarketData.symbol,
                order_by=(
                    MarketData.timestamp.desc(),
                    MarketData.vintage_at.desc(),
                    case((MarketData.contract_month == "main", 0), else_=1),
                    MarketData.ingested_at.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(MarketData.symbol.in_(symbols))
        .subquery()
    )
    return (
        select(MarketData)
        .join(ranked, MarketData.id == ranked.c.id)
        .where(ranked.c.row_number == 1)
    )


def _recent_market_data_statement(symbols: list[str], limit: int):
    pit_ranked = (
        select(
            MarketData.id.label("id"),
            MarketData.symbol.label("symbol"),
            MarketData.timestamp.label("timestamp"),
            func.row_number()
            .over(
                partition_by=(MarketData.symbol, MarketData.timestamp),
                order_by=(
                    MarketData.vintage_at.desc(),
                    case((MarketData.contract_month == "main", 0), else_=1),
                    MarketData.ingested_at.desc(),
                ),
            )
            .label("pit_row_number"),
        )
        .where(MarketData.symbol.in_(symbols))
        .subquery()
    )
    symbol_ranked = (
        select(
            pit_ranked.c.id.label("id"),
            pit_ranked.c.symbol.label("symbol"),
            pit_ranked.c.timestamp.label("timestamp"),
            func.row_number()
            .over(
                partition_by=pit_ranked.c.symbol,
                order_by=pit_ranked.c.timestamp.desc(),
            )
            .label("symbol_row_number"),
        )
        .where(pit_ranked.c.pit_row_number == 1)
        .subquery()
    )
    return (
        select(MarketData)
        .join(symbol_ranked, MarketData.id == symbol_ranked.c.id)
        .where(symbol_ranked.c.symbol_row_number <= limit)
        .order_by(MarketData.symbol.asc(), MarketData.timestamp.desc())
    )


def _parse_market_symbols(value: str) -> list[str]:
    symbols = list(
        dict.fromkeys(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    )
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols must include at least one value")
    if len(symbols) > MAX_BATCH_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"symbols supports at most {MAX_BATCH_SYMBOLS} unique values",
        )
    return symbols
