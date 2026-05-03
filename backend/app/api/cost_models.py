from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cost_snapshot import CostSnapshot
from app.schemas.common import CostChainRead, CostModelRead, CostSimulationRequest, CostSnapshotRead
from app.services.cost_models.cost_chain import FERROUS_CHAIN_ORDER, calculate_cost_chain
from app.services.cost_models.snapshots import (
    FERROUS_SYMBOLS,
    calculate_cost_snapshot,
    current_prices_for_symbols,
    snapshot_ferrous_costs,
)

router = APIRouter(prefix="/api/cost-models", tags=["cost-models"])


@router.get("/{symbol}", response_model=CostModelRead)
async def get_cost_model(symbol: str, session: AsyncSession = Depends(get_db)) -> dict:
    try:
        result = await calculate_cost_snapshot(session, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return cost_model_payload(result.to_snapshot_payload())


@router.get("/{symbol}/history", response_model=list[CostSnapshotRead])
async def get_cost_model_history(
    symbol: str,
    limit: int = Query(default=120, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[CostSnapshot]:
    return list(
        (
            await session.scalars(
                select(CostSnapshot)
                .where(CostSnapshot.symbol == symbol.upper())
                .order_by(CostSnapshot.snapshot_date.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post("/{symbol}/simulate", response_model=CostModelRead)
async def simulate_cost_model(symbol: str, payload: CostSimulationRequest) -> dict:
    normalized = symbol.upper()
    current_prices = {key.upper(): value for key, value in payload.current_prices.items()}
    inputs_by_symbol = {
        key.upper(): dict(value)
        for key, value in payload.inputs_by_symbol.items()
    }
    try:
        chain = calculate_cost_chain(
            symbols=FERROUS_CHAIN_ORDER,
            inputs_by_symbol=inputs_by_symbol,
            current_prices=current_prices,
        )
        result = chain.results[normalized]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported cost model symbol: {symbol}") from exc
    return cost_model_payload(result.to_snapshot_payload())


@router.get("/{symbol}/chain", response_model=CostChainRead)
async def get_cost_chain(symbol: str, session: AsyncSession = Depends(get_db)) -> dict:
    normalized = symbol.upper()
    if normalized not in FERROUS_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Unsupported cost model symbol: {symbol}")
    current_prices = await current_prices_for_symbols(session, FERROUS_SYMBOLS)
    chain = calculate_cost_chain(symbols=FERROUS_CHAIN_ORDER, current_prices=current_prices)
    return {
        "sector": chain.sector,
        "symbols": chain.symbols,
        "results": {
            item: cost_model_payload(result.to_snapshot_payload())
            for item, result in chain.results.items()
        },
    }


@router.post("/snapshots/ferrous", response_model=list[CostSnapshotRead], status_code=status.HTTP_201_CREATED)
async def create_ferrous_cost_snapshots(session: AsyncSession = Depends(get_db)) -> list[CostSnapshot]:
    rows = await snapshot_ferrous_costs(session)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


def cost_model_payload(payload: dict) -> dict:
    return {
        "symbol": payload["symbol"],
        "name": payload["name"],
        "sector": payload["sector"],
        "current_price": payload["current_price"],
        "total_unit_cost": payload["total_unit_cost"],
        "breakevens": {
            "p25": payload["breakeven_p25"],
            "p50": payload["breakeven_p50"],
            "p75": payload["breakeven_p75"],
            "p90": payload["breakeven_p90"],
        },
        "profit_margin": payload["profit_margin"],
        "cost_breakdown": payload["cost_breakdown"],
        "inputs": payload["inputs"],
        "data_sources": payload["data_sources"],
        "uncertainty_pct": payload["uncertainty_pct"],
        "formula_version": payload["formula_version"],
    }
