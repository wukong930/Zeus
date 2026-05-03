from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import publish
from app.services.scenarios import ScenarioRequest, run_scenario_simulation

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class ScenarioSimulationPayload(BaseModel):
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
async def simulate_scenario(payload: ScenarioSimulationPayload) -> dict[str, Any]:
    return run_scenario_simulation(payload.to_service_request()).to_dict()


@router.post("/requests")
async def request_scenario(
    payload: ScenarioSimulationPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    event = await publish(
        "scenario.requested",
        {"request": payload.model_dump()},
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
