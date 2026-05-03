from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.position import Position
from app.services.market_data.pit import get_market_data_pit
from app.services.risk.correlation import build_correlation_matrix
from app.services.risk.stress import STRESS_SCENARIOS, run_stress_test
from app.services.risk.types import RiskLeg, RiskMarketPoint, RiskPosition, StressScenario
from app.services.risk.var import calculate_var

router = APIRouter(prefix="/api/risk", tags=["risk"])


class StressScenarioPayload(BaseModel):
    name: str
    description: str
    shocks: dict[str, float]
    historical: bool = False


class StressRequest(BaseModel):
    scenarios: list[StressScenarioPayload] | None = Field(default=None)


@router.get("/var")
async def get_portfolio_var(
    horizon: int = Query(default=1, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    positions = await _open_positions(session)
    symbols = _position_symbols(positions)
    market_data = await _market_data_for_symbols(session, symbols, limit=252)
    return {"success": True, "data": calculate_var(positions, market_data, horizon=horizon).to_dict()}


@router.get("/stress")
async def get_stress_tests(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    positions = await _open_positions(session)
    results = run_stress_test(positions, STRESS_SCENARIOS)
    return {"success": True, "data": [result.to_dict() for result in results]}


@router.post("/stress")
async def run_custom_stress_tests(
    payload: StressRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    positions = await _open_positions(session)
    scenarios = (
        [
            StressScenario(
                name=scenario.name,
                description=scenario.description,
                shocks=scenario.shocks,
                historical=scenario.historical,
            )
            for scenario in payload.scenarios
        ]
        if payload is not None and payload.scenarios is not None
        else list(STRESS_SCENARIOS)
    )
    results = run_stress_test(positions, scenarios)
    return {"success": True, "data": [result.to_dict() for result in results]}


@router.get("/correlation")
async def get_correlation_matrix(
    symbols: str | None = None,
    window: int = Query(default=60, ge=5, le=252),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if symbols is not None:
        symbol_list = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    else:
        symbol_list = _position_symbols(await _open_positions(session))

    market_data = await _market_data_for_symbols(session, symbol_list, limit=window + 10)
    matrix = build_correlation_matrix(market_data, symbol_list, window=window)
    return {"success": True, "data": matrix.to_dict()}


async def _open_positions(session: AsyncSession) -> list[RiskPosition]:
    rows = list(
        (
            await session.scalars(
                select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
            )
        ).all()
    )
    return [_position_to_risk_position(row) for row in rows]


async def _market_data_for_symbols(
    session: AsyncSession,
    symbols: list[str],
    *,
    limit: int,
) -> dict[str, list[RiskMarketPoint]]:
    market_data: dict[str, list[RiskMarketPoint]] = {}
    for symbol in symbols:
        rows = await get_market_data_pit(session, symbol=symbol, limit=limit)
        market_data[symbol] = [
            RiskMarketPoint(
                symbol=row.symbol,
                timestamp=row.timestamp,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                open_interest=row.open_interest,
            )
            for row in rows
        ]
    return market_data


def _position_to_risk_position(position: Position) -> RiskPosition:
    return RiskPosition(
        id=str(position.id),
        strategy_name=position.strategy_name,
        status=position.status,
        legs=tuple(_leg_from_payload(leg) for leg in position.legs if isinstance(leg, dict)),
    )


def _leg_from_payload(payload: dict[str, Any]) -> RiskLeg:
    asset = str(payload.get("asset") or payload.get("symbol") or "")
    direction = "short" if str(payload.get("direction", "long")).lower() == "short" else "long"
    return RiskLeg(
        asset=asset,
        direction=direction,
        size=_float_from_payload(payload, "size", "quantity", "lots", default=0.0),
        current_price=_float_from_payload(payload, "currentPrice", "current_price", "price", default=0.0),
        entry_price=_optional_float_from_payload(payload, "entryPrice", "entry_price"),
        unit=payload.get("unit"),
        unrealized_pnl=_optional_float_from_payload(payload, "unrealizedPnl", "unrealized_pnl"),
        margin_used=_optional_float_from_payload(payload, "marginUsed", "margin_used"),
    )


def _position_symbols(positions: list[RiskPosition]) -> list[str]:
    return sorted({leg.asset for position in positions for leg in position.legs if leg.asset})


def _optional_float_from_payload(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in payload and payload[key] is not None:
            return float(payload[key])
    return None


def _float_from_payload(payload: dict[str, Any], *keys: str, default: float) -> float:
    value = _optional_float_from_payload(payload, *keys)
    return default if value is None else value
