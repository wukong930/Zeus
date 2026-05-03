from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry_data import IndustryData
from app.models.market_data import MarketData


def _windowed_latest_statement(
    model: type[MarketData] | type[IndustryData],
    partition_columns: list,
    base_statement: Select,
    limit: int,
) -> Select:
    ranked = base_statement.add_columns(
        func.row_number()
        .over(
            partition_by=partition_columns,
            order_by=model.vintage_at.desc(),
        )
        .label("rn")
    ).subquery()

    return select(model).join(ranked, model.id == ranked.c.id).where(ranked.c.rn == 1).limit(limit)


async def get_market_data_pit(
    session: AsyncSession,
    *,
    symbol: str,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
) -> list[MarketData]:
    statement = select(MarketData).where(MarketData.symbol == symbol)
    if as_of is not None:
        statement = statement.where(MarketData.vintage_at <= as_of)
    if start is not None:
        statement = statement.where(MarketData.timestamp >= start)
    if end is not None:
        statement = statement.where(MarketData.timestamp <= end)

    pit_statement = _windowed_latest_statement(
        MarketData,
        [MarketData.symbol, MarketData.contract_month, MarketData.timestamp],
        statement,
        limit,
    ).order_by(MarketData.timestamp.desc())

    return list((await session.scalars(pit_statement)).all())


async def get_industry_data_pit(
    session: AsyncSession,
    *,
    symbol: str,
    data_type: str | None = None,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
) -> list[IndustryData]:
    statement = select(IndustryData).where(IndustryData.symbol == symbol)
    if data_type is not None:
        statement = statement.where(IndustryData.data_type == data_type)
    if as_of is not None:
        statement = statement.where(IndustryData.vintage_at <= as_of)
    if start is not None:
        statement = statement.where(IndustryData.timestamp >= start)
    if end is not None:
        statement = statement.where(IndustryData.timestamp <= end)

    pit_statement = _windowed_latest_statement(
        IndustryData,
        [IndustryData.symbol, IndustryData.data_type, IndustryData.timestamp],
        statement,
        limit,
    ).order_by(IndustryData.timestamp.desc())

    return list((await session.scalars(pit_statement)).all())
