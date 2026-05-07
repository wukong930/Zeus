from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import publish
from app.models.market_data import MarketData
from app.schemas.common import StrictInputModel
from app.services.risk.stress import symbol_prefix
from app.services.scenarios import (
    ScenarioRequest,
    run_scenario_simulation,
    run_scenario_simulation_with_llm_narrative,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class ScenarioSimulationPayload(StrictInputModel):
    target_symbol: str = Field(min_length=1, max_length=20)
    shocks: dict[str, float] = Field(min_length=1)
    base_price: float | None = Field(default=None, gt=0)
    days: int = Field(default=20, ge=1, le=252)
    simulations: int = Field(default=1000, ge=100, le=10000)
    volatility_pct: float | None = Field(default=None, ge=0.001, le=0.2)
    drift_pct: float = Field(default=0.0, ge=-0.8, le=0.8)
    seed: int = Field(default=7, ge=0)
    max_depth: int = Field(default=3, ge=1, le=5)

    @field_validator("shocks")
    @classmethod
    def validate_shocks(cls, value: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for symbol, shock in value.items():
            normalized_symbol = str(symbol).strip().upper()
            if not normalized_symbol:
                continue
            if shock < -0.8 or shock > 0.8:
                raise ValueError("shock values must be between -0.8 and 0.8")
            cleaned[normalized_symbol] = float(shock)
        if not cleaned:
            raise ValueError("at least one non-empty shock symbol is required")
        return cleaned

    def to_service_request(self) -> ScenarioRequest:
        return ScenarioRequest(
            target_symbol=self.target_symbol,
            shocks=self.shocks,
            base_price=self.base_price,
            days=self.days,
            simulations=self.simulations,
            volatility_pct=self.volatility_pct,
            drift_pct=self.drift_pct,
            seed=self.seed,
            max_depth=self.max_depth,
        )


@router.post("/simulate")
async def simulate_scenario(
    payload: ScenarioSimulationPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request, runtime = await resolve_scenario_request_inputs(session, payload.to_service_request())
    return run_scenario_simulation(request, **runtime).to_dict()


@router.post("/simulate/llm")
async def simulate_scenario_with_llm(
    payload: ScenarioSimulationPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request, runtime = await resolve_scenario_request_inputs(session, payload.to_service_request())
    report = await run_scenario_simulation_with_llm_narrative(request, session=session, **runtime)
    return report.to_dict()


@router.post("/requests")
async def request_scenario(
    payload: ScenarioSimulationPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request, runtime = await resolve_scenario_request_inputs(session, payload.to_service_request())
    event = await publish(
        "scenario.requested",
        {
            "request": asdict(request),
            "runtime": {
                "base_price_source": runtime["base_price_source"],
                "unavailable_sections": list(runtime["unavailable_sections"]),
            },
            "use_llm_narrative": True,
        },
        source="scenario-api",
        session=session,
    )
    await session.commit()
    return {
        "success": True,
        "event_id": str(event.id),
        "correlation_id": event.correlation_id,
        "status": "queued",
    }


async def resolve_scenario_request_inputs(
    session: AsyncSession,
    request: ScenarioRequest,
) -> tuple[ScenarioRequest, dict[str, Any]]:
    if request.base_price is not None:
        return request, {"base_price_source": "provided", "unavailable_sections": ()}

    latest = await latest_market_price_for_scenario(session, request.target_symbol)
    if latest is not None:
        return (
            replace(request, base_price=latest),
            {"base_price_source": "runtime_market_data", "unavailable_sections": ()},
        )
    return (
        request,
        {
            "base_price_source": "default_static",
            "unavailable_sections": ("market_price_unavailable",),
        },
    )


async def latest_market_price_for_scenario(
    session: AsyncSession,
    target_symbol: str,
) -> float | None:
    root_symbol = symbol_prefix(target_symbol)
    if not root_symbol:
        return None
    row = (
        await session.scalars(
            select(MarketData)
            .where(
                or_(
                    MarketData.symbol == root_symbol,
                    MarketData.symbol.like(f"{root_symbol}%"),
                )
            )
            .order_by(MarketData.timestamp.desc(), MarketData.vintage_at.desc())
            .limit(1)
        )
    ).first()
    if row is None or row.close <= 0:
        return None
    return float(row.close)
