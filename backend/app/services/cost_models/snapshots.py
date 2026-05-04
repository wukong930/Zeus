from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commodity_config import CommodityConfig
from app.models.cost_snapshot import CostSnapshot
from app.models.market_data import MarketData
from app.services.cost_models.configs import ALL_COST_FORMULAS
from app.services.cost_models.cost_chain import (
    FERROUS_CHAIN_ORDER,
    RUBBER_CHAIN_ORDER,
    UPSTREAM_BY_SYMBOL,
    calculate_cost_chain,
    calculate_symbol_cost,
    chain_order_for_symbol,
)
from app.services.cost_models.framework import CostModelResult

FERROUS_SYMBOLS = FERROUS_CHAIN_ORDER
RUBBER_SYMBOLS = RUBBER_CHAIN_ORDER
ALL_COST_SYMBOLS = FERROUS_SYMBOLS + RUBBER_SYMBOLS


async def latest_market_price(session: AsyncSession, symbol: str) -> float | None:
    prices = await current_prices_for_symbols(session, (symbol,))
    return prices.get(symbol)


async def current_prices_for_symbols(
    session: AsyncSession,
    symbols: tuple[str, ...],
) -> dict[str, float | None]:
    if not symbols:
        return {}

    normalized_symbols = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
    ranked_prices = (
        select(
            MarketData.symbol.label("symbol"),
            MarketData.close.label("close"),
            func.row_number()
            .over(
                partition_by=MarketData.symbol,
                order_by=(MarketData.timestamp.desc(), MarketData.vintage_at.desc()),
            )
            .label("rn"),
        )
        .where(MarketData.symbol.in_(normalized_symbols))
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked_prices.c.symbol, ranked_prices.c.close).where(ranked_prices.c.rn == 1)
        )
    ).all()
    prices_by_symbol = {symbol: float(close) for symbol, close in rows}
    return {symbol: prices_by_symbol.get(symbol.upper()) for symbol in symbols}


async def ensure_commodity_configs(
    session: AsyncSession,
    *,
    symbols: tuple[str, ...] = ALL_COST_SYMBOLS,
) -> int:
    existing = set(
        (
            await session.scalars(
                select(CommodityConfig.symbol).where(CommodityConfig.symbol.in_(symbols))
            )
        ).all()
    )
    created = 0
    for symbol in symbols:
        if symbol in existing:
            continue
        formula = ALL_COST_FORMULAS[symbol]
        session.add(
            CommodityConfig(
                symbol=symbol,
                name=formula.name,
                sector=formula.sector,
                cost_formula={"name": formula.__class__.__name__, "version": formula.version},
                cost_chain=UPSTREAM_BY_SYMBOL.get(symbol, []),
                parameters={"public_fallback": True},
                data_sources=[
                    {
                        "name": "public_fallback",
                        "type": "manual_seed",
                        "quality": "rough",
                    }
                ],
                uncertainty_pct=formula.uncertainty_pct,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def calculate_cost_snapshot(
    session: AsyncSession,
    symbol: str,
    *,
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
) -> CostModelResult:
    normalized = symbol.upper()
    if current_prices is None:
        current_prices = await current_prices_for_symbols(session, chain_order_for_symbol(normalized))
    return calculate_symbol_cost(
        normalized,
        inputs_by_symbol=inputs_by_symbol,
        current_prices=current_prices,
    )


async def write_cost_snapshot(
    session: AsyncSession,
    result: CostModelResult,
    *,
    snapshot_date: date | None = None,
) -> CostSnapshot:
    effective_date = snapshot_date or datetime.now(timezone.utc).date()
    row = (
        await session.scalars(
            select(CostSnapshot)
            .where(
                CostSnapshot.symbol == result.symbol,
                CostSnapshot.snapshot_date == effective_date,
            )
            .limit(1)
        )
    ).first()
    payload = result.to_snapshot_payload()
    if row is None:
        row = CostSnapshot(
            snapshot_date=effective_date,
            **payload,
        )
        session.add(row)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    await session.flush()
    return row


async def snapshot_ferrous_costs(
    session: AsyncSession,
    *,
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
    snapshot_date: date | None = None,
) -> list[CostSnapshot]:
    return await snapshot_costs(
        session,
        symbols=FERROUS_SYMBOLS,
        inputs_by_symbol=inputs_by_symbol,
        current_prices=current_prices,
        snapshot_date=snapshot_date,
    )


async def snapshot_rubber_costs(
    session: AsyncSession,
    *,
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
    snapshot_date: date | None = None,
) -> list[CostSnapshot]:
    return await snapshot_costs(
        session,
        symbols=RUBBER_SYMBOLS,
        inputs_by_symbol=inputs_by_symbol,
        current_prices=current_prices,
        snapshot_date=snapshot_date,
    )


async def snapshot_costs(
    session: AsyncSession,
    *,
    symbols: tuple[str, ...],
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
    snapshot_date: date | None = None,
) -> list[CostSnapshot]:
    await ensure_commodity_configs(session, symbols=symbols)
    if current_prices is None:
        current_prices = await current_prices_for_symbols(session, symbols)
    chain = calculate_cost_chain(
        symbols=symbols,
        inputs_by_symbol=inputs_by_symbol,
        current_prices=current_prices,
    )
    rows: list[CostSnapshot] = []
    for symbol in symbols:
        rows.append(
            await write_cost_snapshot(
                session,
                chain.results[symbol],
                snapshot_date=snapshot_date,
            )
        )
    return rows


def cost_snapshot_context_payload(row: CostSnapshot) -> dict[str, Any]:
    snapshot_time = row.created_at or datetime.combine(
        row.snapshot_date,
        datetime.min.time(),
        timezone.utc,
    )
    return {
        "symbol": row.symbol,
        "timestamp": snapshot_time.isoformat(),
        "snapshot_date": row.snapshot_date.isoformat(),
        "current_price": row.current_price,
        "total_unit_cost": row.total_unit_cost,
        "breakeven_p25": row.breakeven_p25,
        "breakeven_p50": row.breakeven_p50,
        "breakeven_p75": row.breakeven_p75,
        "breakeven_p90": row.breakeven_p90,
        "profit_margin": row.profit_margin,
        "uncertainty_pct": row.uncertainty_pct,
    }


def build_cost_signal_context(symbol: str, rows: list[CostSnapshot]) -> dict[str, Any] | None:
    normalized = symbol.upper()
    ordered = sorted(
        (row for row in rows if row.symbol == normalized),
        key=lambda row: row.snapshot_date,
    )
    if not ordered:
        return None

    latest = ordered[-1]
    timestamp = latest.created_at or datetime.combine(
        latest.snapshot_date,
        datetime.min.time(),
        timezone.utc,
    )
    return {
        "symbol1": normalized,
        "category": latest.sector,
        "timestamp": timestamp.isoformat(),
        "regime": "cost_model",
        "cost_snapshots": [cost_snapshot_context_payload(row) for row in ordered],
    }


async def cost_signal_contexts(
    session: AsyncSession,
    *,
    symbols: tuple[str, ...] = FERROUS_SYMBOLS,
    limit_per_symbol: int = 20,
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for symbol in symbols:
        rows = list(
            (
                await session.scalars(
                    select(CostSnapshot)
                    .where(CostSnapshot.symbol == symbol)
                    .order_by(CostSnapshot.snapshot_date.desc())
                    .limit(limit_per_symbol)
                )
            ).all()
        )
        context = build_cost_signal_context(symbol, rows)
        if context is not None:
            contexts.append(context)
    return contexts


async def latest_cost_snapshot(session: AsyncSession, symbol: str) -> CostSnapshot | None:
    return (
        await session.scalars(
            select(CostSnapshot)
            .where(CostSnapshot.symbol == symbol.upper())
            .order_by(CostSnapshot.snapshot_date.desc(), CostSnapshot.created_at.desc())
            .limit(1)
        )
    ).first()
