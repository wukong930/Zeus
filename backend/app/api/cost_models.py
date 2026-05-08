from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cost_snapshot import CostSnapshot
from app.schemas.common import (
    CostChainRead,
    CostModelRead,
    CostQualityReportRead,
    CostSimulationRequest,
    CostSnapshotRead,
    MAX_COST_SIMULATION_SYMBOL_LENGTH,
    normalize_commodity_symbol,
)
from app.services.cost_models.cost_chain import calculate_cost_chain, chain_order_for_symbol
from app.services.cost_models.quality import run_ferrous_quality_report, run_rubber_quality_report
from app.services.cost_models.snapshots import (
    calculate_cost_snapshot,
    cost_histories_for_symbols,
    current_prices_for_symbols,
    snapshot_ferrous_costs,
    snapshot_rubber_costs,
)

router = APIRouter(prefix="/api/cost-models", tags=["cost-models"])
MAX_COST_HISTORY_SYMBOLS = 40
MAX_COST_HISTORY_SYMBOL_QUERY_LENGTH = 1000


@router.get("/quality/ferrous", response_model=CostQualityReportRead)
async def get_ferrous_cost_quality_report(session: AsyncSession = Depends(get_db)) -> dict:
    report = await run_ferrous_quality_report(session)
    return report.to_dict()


@router.get("/quality/rubber", response_model=CostQualityReportRead)
async def get_rubber_cost_quality_report(session: AsyncSession = Depends(get_db)) -> dict:
    report = await run_rubber_quality_report(session)
    return report.to_dict()


@router.get("/histories", response_model=dict[str, list[CostSnapshotRead]])
async def get_cost_model_histories(
    symbols: str = Query(..., min_length=1, max_length=MAX_COST_HISTORY_SYMBOL_QUERY_LENGTH),
    limit: int = Query(default=30, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[CostSnapshot]]:
    return await cost_histories_for_symbols(
        session,
        symbols=_parse_cost_symbols(symbols),
        limit_per_symbol=limit,
    )


@router.get("/{symbol}", response_model=CostModelRead)
async def get_cost_model(
    symbol: str = Path(..., min_length=1, max_length=MAX_COST_SIMULATION_SYMBOL_LENGTH),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await calculate_cost_snapshot(session, normalize_commodity_symbol(symbol))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return cost_model_payload(result.to_snapshot_payload())


@router.get("/{symbol}/history", response_model=list[CostSnapshotRead])
async def get_cost_model_history(
    symbol: str = Path(..., min_length=1, max_length=MAX_COST_SIMULATION_SYMBOL_LENGTH),
    limit: int = Query(default=120, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[CostSnapshot]:
    try:
        normalized = normalize_commodity_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported cost model symbol: {symbol}") from exc
    return list(
        (
            await session.scalars(
                select(CostSnapshot)
                .where(CostSnapshot.symbol == normalized)
                .order_by(CostSnapshot.snapshot_date.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post("/{symbol}/simulate", response_model=CostModelRead)
async def simulate_cost_model(
    payload: CostSimulationRequest,
    symbol: str = Path(..., min_length=1, max_length=MAX_COST_SIMULATION_SYMBOL_LENGTH),
) -> dict:
    try:
        normalized = normalize_commodity_symbol(symbol)
        current_prices = payload.current_prices
        inputs_by_symbol = {key: dict(value) for key, value in payload.inputs_by_symbol.items()}
        chain_order = chain_order_for_symbol(normalized)
        chain = calculate_cost_chain(
            symbols=chain_order,
            inputs_by_symbol=inputs_by_symbol,
            current_prices=current_prices,
        )
        result = chain.results[normalized]
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported cost model symbol: {symbol}") from exc
    return cost_model_payload(result.to_snapshot_payload())


@router.get("/{symbol}/chain", response_model=CostChainRead)
async def get_cost_chain(
    symbol: str = Path(..., min_length=1, max_length=MAX_COST_SIMULATION_SYMBOL_LENGTH),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        normalized = normalize_commodity_symbol(symbol)
        chain_order = chain_order_for_symbol(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported cost model symbol: {symbol}") from exc
    current_prices = await current_prices_for_symbols(session, chain_order)
    chain = calculate_cost_chain(symbols=chain_order, current_prices=current_prices)
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


@router.post("/snapshots/rubber", response_model=list[CostSnapshotRead], status_code=status.HTTP_201_CREATED)
async def create_rubber_cost_snapshots(session: AsyncSession = Depends(get_db)) -> list[CostSnapshot]:
    rows = await snapshot_rubber_costs(session)
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


def _parse_cost_symbols(value: str) -> tuple[str, ...]:
    raw_symbols = tuple(
        dict.fromkeys(symbol.strip() for symbol in value.split(",") if symbol.strip())
    )
    if len(raw_symbols) > MAX_COST_HISTORY_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"symbols supports at most {MAX_COST_HISTORY_SYMBOLS} unique values",
        )
    if oversized := [
        symbol for symbol in raw_symbols if len(symbol) > MAX_COST_SIMULATION_SYMBOL_LENGTH
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "symbol entries can be at most "
                f"{MAX_COST_SIMULATION_SYMBOL_LENGTH} characters: {','.join(oversized[:3])}"
            ),
        )
    try:
        symbols = tuple(
            dict.fromkeys(
                normalize_commodity_symbol(symbol)
                for symbol in raw_symbols
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols must include at least one value")
    if len(symbols) > MAX_COST_HISTORY_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"symbols supports at most {MAX_COST_HISTORY_SYMBOLS} unique values",
        )
    return symbols
