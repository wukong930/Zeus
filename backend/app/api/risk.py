from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.position import Position
from app.schemas.common import StrictInputModel
from app.services.risk.correlation import build_correlation_matrix
from app.services.risk.market_data import load_risk_market_data
from app.services.risk.stress import STRESS_SCENARIOS, run_stress_test, symbol_prefix
from app.services.risk.types import RiskLeg, RiskPosition, StressScenario
from app.services.risk.var import calculate_var

router = APIRouter(prefix="/api/risk", tags=["risk"])

VAR_MIN_MARKET_POINTS = 11
CORRELATION_MIN_MARKET_POINTS = 4


class StressScenarioPayload(StrictInputModel):
    name: str
    description: str
    shocks: dict[str, float]
    historical: bool = False


class StressRequest(StrictInputModel):
    scenarios: list[StressScenarioPayload] | None = Field(default=None)


@router.get("/var")
async def get_portfolio_var(
    horizon: int = Query(default=1, ge=1, le=20),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    positions = await _open_positions(session)
    symbols = _position_symbols(positions)
    market_data = await load_risk_market_data(session, symbols, limit=252)
    unavailable_sections = _var_unavailable_sections(positions, symbols, market_data)
    return _risk_envelope(
        calculate_var(positions, market_data, horizon=horizon).to_dict(),
        unavailable_sections=unavailable_sections,
    )


@router.get("/stress")
async def get_stress_tests(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    positions = await _open_positions(session)
    results = run_stress_test(positions, STRESS_SCENARIOS)
    return _risk_envelope(
        [result.to_dict() for result in results],
        unavailable_sections=_stress_unavailable_sections(positions, list(STRESS_SCENARIOS)),
    )


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
    return _risk_envelope(
        [result.to_dict() for result in results],
        unavailable_sections=_stress_unavailable_sections(positions, scenarios),
    )


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

    market_data = await load_risk_market_data(session, symbol_list, limit=window + 10)
    matrix = build_correlation_matrix(market_data, symbol_list, window=window)
    return _risk_envelope(
        matrix.to_dict(),
        unavailable_sections=_correlation_unavailable_sections(symbol_list, market_data),
    )


def _risk_envelope(data: Any, *, unavailable_sections: list[str] | None = None) -> dict[str, Any]:
    sections = list(dict.fromkeys(unavailable_sections or []))
    return {
        "success": True,
        "data": data,
        "degraded": bool(sections),
        "unavailable_sections": sections,
    }


async def _open_positions(session: AsyncSession) -> list[RiskPosition]:
    rows = list(
        (
            await session.scalars(
                select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
            )
        ).all()
    )
    return [_position_to_risk_position(row) for row in rows]


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


def _var_unavailable_sections(
    positions: list[RiskPosition],
    symbols: list[str],
    market_data: dict[str, list[Any]],
) -> list[str]:
    if not positions:
        return []
    if not symbols:
        return ["positions_without_risk_symbols"]

    missing = [symbol for symbol in symbols if len(market_data.get(symbol, [])) == 0]
    insufficient = [
        symbol
        for symbol in symbols
        if 0 < len(market_data.get(symbol, [])) < VAR_MIN_MARKET_POINTS
    ]
    sections: list[str] = []
    if missing:
        sections.append(f"market_data_missing:{','.join(missing)}")
    if insufficient:
        sections.append(f"market_data_insufficient:{','.join(insufficient)}")
    return sections


def _stress_unavailable_sections(
    positions: list[RiskPosition],
    scenarios: list[StressScenario],
) -> list[str]:
    if not positions:
        return []

    open_legs = [
        leg
        for position in positions
        if position.status == "open"
        for leg in position.legs
    ]
    if not open_legs:
        return ["positions_without_risk_legs"]

    unvalued = [
        leg.asset or "unknown"
        for leg in open_legs
        if not leg.asset or leg.size == 0 or leg.current_price == 0
    ]
    covered_prefixes = {
        prefix
        for scenario in scenarios
        for prefix in scenario.shocks
        if scenario.shocks.get(prefix) != 0
    }
    uncovered = [
        leg.asset
        for leg in open_legs
        if leg.asset and symbol_prefix(leg.asset) not in covered_prefixes
    ]

    sections: list[str] = []
    if unvalued:
        sections.append(f"positions_without_valued_legs:{','.join(sorted(set(unvalued)))}")
    if uncovered:
        sections.append(f"stress_uncovered_symbols:{','.join(sorted(set(uncovered)))}")
    return sections


def _correlation_unavailable_sections(
    symbols: list[str],
    market_data: dict[str, list[Any]],
) -> list[str]:
    if not symbols:
        return []

    sections: list[str] = []
    if len(symbols) < 2:
        sections.append("correlation_insufficient_symbols")

    missing = [symbol for symbol in symbols if len(market_data.get(symbol, [])) == 0]
    insufficient = [
        symbol
        for symbol in symbols
        if 0 < len(market_data.get(symbol, [])) < CORRELATION_MIN_MARKET_POINTS
    ]
    if missing:
        sections.append(f"correlation_data_missing:{','.join(missing)}")
    if insufficient:
        sections.append(f"correlation_data_insufficient:{','.join(insufficient)}")
    return sections


def _optional_float_from_payload(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in payload and payload[key] is not None:
            return float(payload[key])
    return None


def _float_from_payload(payload: dict[str, Any], *keys: str, default: float) -> float:
    value = _optional_float_from_payload(payload, *keys)
    return default if value is None else value
