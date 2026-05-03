from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry_data import IndustryData
from app.models.market_data import MarketData
from app.schemas.common import IndustryDataCreate, MarketDataCreate


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def market_source_key(symbol: str, contract_month: str, timestamp: datetime) -> str:
    return f"{symbol}:{contract_month}:{_compact_timestamp(timestamp)}"


def industry_source_key(symbol: str, data_type: str, timestamp: datetime) -> str:
    return f"{symbol}:{data_type}:{_compact_timestamp(timestamp)}"


def prepare_market_data_rows(
    payloads: Iterable[MarketDataCreate],
    *,
    vintage_at: datetime | None = None,
) -> list[MarketData]:
    vintage = vintage_at or datetime.now(timezone.utc)
    rows: list[MarketData] = []

    for payload in payloads:
        data = payload.model_dump(exclude_none=True)
        data["vintage_at"] = payload.vintage_at or vintage
        data["source_key"] = payload.source_key or market_source_key(
            payload.symbol,
            payload.contract_month,
            payload.timestamp,
        )
        rows.append(MarketData(**data))

    return rows


def prepare_industry_data_rows(
    payloads: Iterable[IndustryDataCreate],
    *,
    vintage_at: datetime | None = None,
) -> list[IndustryData]:
    vintage = vintage_at or datetime.now(timezone.utc)
    rows: list[IndustryData] = []

    for payload in payloads:
        data = payload.model_dump(exclude_none=True)
        data["vintage_at"] = payload.vintage_at or vintage
        data["source_key"] = payload.source_key or industry_source_key(
            payload.symbol,
            payload.data_type,
            payload.timestamp,
        )
        rows.append(IndustryData(**data))

    return rows


async def append_market_data(
    session: AsyncSession,
    payloads: Iterable[MarketDataCreate],
    *,
    vintage_at: datetime | None = None,
) -> list[MarketData]:
    rows = prepare_market_data_rows(payloads, vintage_at=vintage_at)
    session.add_all(rows)
    await session.flush()
    return rows


async def append_industry_data(
    session: AsyncSession,
    payloads: Iterable[IndustryDataCreate],
    *,
    vintage_at: datetime | None = None,
) -> list[IndustryData]:
    rows = prepare_industry_data_rows(payloads, vintage_at=vintage_at)
    session.add_all(rows)
    await session.flush()
    return rows
