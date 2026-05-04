from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import MarketData
from app.services.risk.types import RiskMarketPoint


async def load_risk_market_data(
    session: AsyncSession,
    symbols: Sequence[str],
    *,
    limit: int,
) -> dict[str, list[RiskMarketPoint]]:
    requested_symbols = tuple(dict.fromkeys(symbol for symbol in symbols if symbol))
    market_data: dict[str, list[RiskMarketPoint]] = {symbol: [] for symbol in requested_symbols}
    if not requested_symbols:
        return market_data

    rows = list(
        (
            await session.scalars(
                _risk_market_data_statement(requested_symbols=requested_symbols, limit=limit)
            )
        ).all()
    )
    for row in rows:
        market_data.setdefault(row.symbol, []).append(_risk_market_point(row))
    return market_data


def _risk_market_data_statement(*, requested_symbols: tuple[str, ...], limit: int):
    pit_ranked = (
        select(
            MarketData.id.label("id"),
            func.row_number()
            .over(
                partition_by=(
                    MarketData.symbol,
                    MarketData.contract_month,
                    MarketData.timestamp,
                ),
                order_by=MarketData.vintage_at.desc(),
            )
            .label("pit_rn"),
        )
        .where(MarketData.symbol.in_(requested_symbols))
        .subquery()
    )
    symbol_ranked = (
        select(
            MarketData.id.label("id"),
            MarketData.symbol.label("symbol"),
            func.row_number()
            .over(
                partition_by=MarketData.symbol,
                order_by=(
                    MarketData.timestamp.desc(),
                    MarketData.contract_month.asc(),
                    MarketData.vintage_at.desc(),
                ),
            )
            .label("symbol_rn"),
        )
        .join(pit_ranked, MarketData.id == pit_ranked.c.id)
        .where(pit_ranked.c.pit_rn == 1)
        .subquery()
    )
    return (
        select(MarketData)
        .join(symbol_ranked, MarketData.id == symbol_ranked.c.id)
        .where(symbol_ranked.c.symbol_rn <= limit)
        .order_by(MarketData.symbol.asc(), MarketData.timestamp.desc(), MarketData.contract_month.asc())
    )


def _risk_market_point(row: MarketData) -> RiskMarketPoint:
    return RiskMarketPoint(
        symbol=row.symbol,
        timestamp=row.timestamp,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        open_interest=row.open_interest,
    )
