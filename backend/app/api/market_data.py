from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.market_data import MarketData
from app.schemas.common import MAX_INGEST_SYMBOL_LENGTH, MarketDataCreate, MarketDataRead
from app.services.etl.writers import append_market_data
from app.services.market_data.pit import get_market_data_pit
from app.services.symbols import normalize_root_symbol

router = APIRouter(prefix="/api/market-data", tags=["market-data"])
MAX_BATCH_SYMBOLS = 50
MAX_MARKET_SYMBOL_QUERY_LENGTH = 2000
MARKET_DATA_CACHE_TTL_SECONDS = 12
MARKET_DATA_CACHE_MAX_ENTRIES = 128

MarketDataCacheKey = tuple[object, ...]
_MARKET_DATA_CACHE: dict[MarketDataCacheKey, tuple[datetime, list[MarketDataRead]]] = {}


@router.get("", response_model=list[MarketDataRead])
async def list_market_data(
    symbol: str = Query(..., min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    before: datetime | None = Query(default=None),
    before_contract_month: str | None = Query(default=None, max_length=20),
    before_id: UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_db),
) -> list[MarketData]:
    normalized_symbol = normalize_root_symbol(symbol)
    if normalized_symbol is None:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")
    return await get_market_data_pit(
        session,
        symbol=normalized_symbol,
        as_of=as_of,
        start=start,
        end=end,
        before=before,
        before_contract_month=before_contract_month,
        before_id=before_id,
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
    _clear_market_data_cache()
    return row


@router.get("/latest", response_model=list[MarketDataRead])
async def get_latest_market_data_batch(
    symbols: str = Query(..., min_length=1, max_length=MAX_MARKET_SYMBOL_QUERY_LENGTH),
    refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> list[MarketDataRead]:
    parsed_symbols = _parse_market_symbols(symbols)
    cache_key = _market_data_cache_key("latest", parsed_symbols)
    if not refresh:
        cached = _market_data_cache_get(cache_key)
        if cached is not None:
            return cached

    rows = _market_data_read_rows(await latest_market_data_for_symbols(session, parsed_symbols))
    _market_data_cache_set(cache_key, rows)
    return rows


@router.get("/recent", response_model=list[MarketDataRead])
async def get_recent_market_data_batch(
    symbols: str = Query(..., min_length=1, max_length=MAX_MARKET_SYMBOL_QUERY_LENGTH),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=200),
    refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> list[MarketDataRead]:
    parsed_symbols = _parse_market_symbols(symbols)
    cache_key = _market_data_cache_key("recent", parsed_symbols, limit=limit, before=before)
    if not refresh:
        cached = _market_data_cache_get(cache_key)
        if cached is not None:
            return cached

    rows = _market_data_read_rows(
        await recent_market_data_for_symbols(
            session,
            parsed_symbols,
            before=before,
            limit=limit,
        )
    )
    _market_data_cache_set(cache_key, rows)
    return rows


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
    symbol: str = Path(..., min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    session: AsyncSession = Depends(get_db),
) -> MarketData:
    normalized_symbol = normalize_root_symbol(symbol)
    if normalized_symbol is None:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")
    rows = await latest_market_data_for_symbols(session, [normalized_symbol])
    if not rows:
        raise HTTPException(status_code=404, detail="Market data row not found")
    return rows[0]


async def latest_market_data_for_symbols(
    session: AsyncSession,
    symbols: list[str],
) -> list[MarketData]:
    requested_symbols = _normalize_market_symbols(symbols)
    if not requested_symbols:
        return []

    rows = list((await session.scalars(_latest_market_data_statement(requested_symbols))).all())
    rows_by_symbol = {row.symbol.upper(): row for row in rows}
    return [rows_by_symbol[symbol] for symbol in requested_symbols if symbol in rows_by_symbol]


async def recent_market_data_for_symbols(
    session: AsyncSession,
    symbols: list[str],
    *,
    before: datetime | None = None,
    limit: int,
) -> list[MarketData]:
    requested_symbols = _normalize_market_symbols(symbols)
    if not requested_symbols:
        return []

    return list(
        (
            await session.scalars(
                _recent_market_data_statement(requested_symbols, limit, before=before)
            )
        ).all()
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
                    MarketData.id.desc(),
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


def _recent_market_data_statement(symbols: list[str], limit: int, *, before: datetime | None = None):
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
                    MarketData.id.desc(),
                ),
            )
            .label("pit_row_number"),
        )
        .where(MarketData.symbol.in_(symbols))
    )
    if before is not None:
        # A bare timestamp cursor is sufficient here (unlike the other list
        # endpoints): pit_ranked dedups to one row per (symbol, timestamp), so
        # within each symbol's stream timestamps are unique and `timestamp < before`
        # cannot skip a tied row at the page boundary.
        pit_ranked = pit_ranked.where(MarketData.timestamp < before)
    pit_ranked = pit_ranked.subquery()  # type: ignore[assignment]  # idiomatic Select -> Subquery
    symbol_ranked = (
        select(
            pit_ranked.c.id.label("id"),
            pit_ranked.c.symbol.label("symbol"),
            pit_ranked.c.timestamp.label("timestamp"),
            func.row_number()
            .over(
                partition_by=pit_ranked.c.symbol,
                order_by=(pit_ranked.c.timestamp.desc(), pit_ranked.c.id.desc()),
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
        .order_by(MarketData.symbol.asc(), MarketData.timestamp.desc(), MarketData.id.desc())
    )


def _parse_market_symbols(value: str) -> list[str]:
    symbols = _normalize_market_symbols(value.split(","))
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols must include at least one value")
    if len(symbols) > MAX_BATCH_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"symbols supports at most {MAX_BATCH_SYMBOLS} unique values",
        )
    if oversized := [symbol for symbol in symbols if len(symbol) > MAX_INGEST_SYMBOL_LENGTH]:
        raise HTTPException(
            status_code=400,
            detail=(
                "symbol entries can be at most "
                f"{MAX_INGEST_SYMBOL_LENGTH} characters: {','.join(oversized[:3])}"
            ),
        )
    return symbols


def _market_data_cache_key(
    kind: str,
    symbols: list[str],
    *,
    limit: int | None = None,
    before: datetime | None = None,
) -> MarketDataCacheKey:
    normalized_symbols = tuple(_normalize_market_symbols(symbols))
    return (kind, normalized_symbols, limit, before.isoformat() if before is not None else None)


def _normalize_market_symbols(symbols: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    return list(
        dict.fromkeys(
            normalized
            for symbol in symbols
            if (normalized := normalize_root_symbol(symbol)) is not None
        )
    )


def _market_data_cache_get(
    key: MarketDataCacheKey,
    *,
    now: datetime | None = None,
) -> list[MarketDataRead] | None:
    current = now or datetime.now(timezone.utc)
    cached = _MARKET_DATA_CACHE.get(key)
    if cached is None:
        return None
    cached_at, rows = cached
    if (current - cached_at).total_seconds() > MARKET_DATA_CACHE_TTL_SECONDS:
        _MARKET_DATA_CACHE.pop(key, None)
        return None
    return [row.model_copy(deep=True) for row in rows]


def _market_data_cache_set(
    key: MarketDataCacheKey,
    rows: list[MarketDataRead],
    *,
    now: datetime | None = None,
) -> None:
    if len(_MARKET_DATA_CACHE) >= MARKET_DATA_CACHE_MAX_ENTRIES and key not in _MARKET_DATA_CACHE:
        oldest_key = min(_MARKET_DATA_CACHE, key=lambda item: _MARKET_DATA_CACHE[item][0])
        _MARKET_DATA_CACHE.pop(oldest_key, None)
    _MARKET_DATA_CACHE[key] = (
        now or datetime.now(timezone.utc),
        [row.model_copy(deep=True) for row in rows],
    )


def _market_data_read_rows(rows: Sequence[MarketData | MarketDataRead]) -> list[MarketDataRead]:
    return [
        row if isinstance(row, MarketDataRead) else MarketDataRead.model_validate(row)
        for row in rows
    ]


def _clear_market_data_cache() -> None:
    _MARKET_DATA_CACHE.clear()
