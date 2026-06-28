from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
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
            order_by=(model.vintage_at.desc(), model.id.desc()),
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
    statement = _market_data_pit_statement(
        symbol=symbol,
        as_of=as_of,
        start=start,
        end=end,
        limit=limit,
    )

    return list((await session.scalars(statement)).all())


def _market_data_pit_statement(
    *,
    symbol: str,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
) -> Select:
    statement = select(MarketData).where(MarketData.symbol == symbol)
    if as_of is not None:
        statement = statement.where(MarketData.vintage_at <= as_of)
    if start is not None:
        statement = statement.where(MarketData.timestamp >= start)
    if end is not None:
        statement = statement.where(MarketData.timestamp <= end)

    return _windowed_latest_statement(
        MarketData,
        [MarketData.symbol, MarketData.contract_month, MarketData.timestamp],
        statement,
        limit,
    ).order_by(MarketData.timestamp.desc(), MarketData.contract_month.asc(), MarketData.id.desc())


async def get_industry_data_pit(
    session: AsyncSession,
    *,
    symbol: str,
    data_type: str | None = None,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    before: datetime | None = None,
    before_id: UUID | None = None,
    limit: int = 500,
) -> list[IndustryData]:
    statement = _industry_data_pit_statement(
        symbol=symbol,
        data_type=data_type,
        as_of=as_of,
        start=start,
        end=end,
        before=before,
        before_id=before_id,
        limit=limit,
    )

    return list((await session.scalars(statement)).all())


def _industry_data_pit_statement(
    *,
    symbol: str,
    data_type: str | None = None,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    before: datetime | None = None,
    before_id: UUID | None = None,
    limit: int = 500,
) -> Select:
    statement = select(IndustryData).where(IndustryData.symbol == symbol)
    if data_type is not None:
        statement = statement.where(IndustryData.data_type == data_type)
    if as_of is not None:
        statement = statement.where(IndustryData.vintage_at <= as_of)
    if start is not None:
        statement = statement.where(IndustryData.timestamp >= start)
    if end is not None:
        statement = statement.where(IndustryData.timestamp <= end)
    if before is not None:
        if before_id is not None:
            statement = statement.where(
                or_(
                    IndustryData.timestamp < before,
                    and_(IndustryData.timestamp == before, IndustryData.id < before_id),
                )
            )
        else:
            statement = statement.where(IndustryData.timestamp < before)

    return _windowed_latest_statement(
        IndustryData,
        [IndustryData.symbol, IndustryData.data_type, IndustryData.timestamp],
        statement,
        limit,
    ).order_by(IndustryData.timestamp.desc(), IndustryData.id.desc())
