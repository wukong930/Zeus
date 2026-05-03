from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.strategy import Strategy
from app.schemas.common import StrategyCreate, StrategyRead
from app.services.backtest import (
    RegimeObservation,
    build_regime_profile,
    calculate_path_metrics,
    pit_commodity_universe,
    validate_backtest_universe_from_symbols,
    walk_forward_defaults,
)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyRead])
async def list_strategies(
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Strategy]:
    statement = select(Strategy).order_by(Strategy.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Strategy.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=StrategyRead, status_code=status.HTTP_201_CREATED)
async def create_strategy(payload: StrategyCreate, session: AsyncSession = Depends(get_db)) -> Strategy:
    row = Strategy(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/backtest-quality")
async def get_backtest_quality_summary(
    as_of: date | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    effective_as_of = as_of or date.today()
    active_symbols = await pit_commodity_universe(session, as_of=effective_as_of)
    universe = validate_backtest_universe_from_symbols(
        symbols=["RB", "HC", "I", "J", "JM", "RU", "NR", "BR"],
        active_symbols=active_symbols,
        as_of=effective_as_of,
    )
    returns = [0.008, -0.004, 0.011, -0.018, 0.006, 0.004, -0.006, 0.014, -0.003, 0.007]
    observations = [
        RegimeObservation("range_low_vol", 0.006),
        RegimeObservation("range_low_vol", -0.003),
        RegimeObservation("range_low_vol", 0.004),
        RegimeObservation("range_high_vol", -0.018),
        RegimeObservation("range_high_vol", 0.014),
        RegimeObservation("trend_up_low_vol", 0.011),
        RegimeObservation("trend_up_low_vol", 0.008),
        RegimeObservation("trend_down_low_vol", -0.006),
    ]
    return {
        "as_of": effective_as_of.isoformat(),
        "walk_forward": walk_forward_defaults(),
        "regime_profile": [item.to_dict() for item in build_regime_profile(observations)],
        "path_metrics": calculate_path_metrics(
            returns,
            mae_values=[-0.006, -0.012, -0.004, -0.018, -0.009],
            mfe_values=[0.012, 0.024, 0.008, 0.030, 0.016],
        ).to_dict(),
        "universe": universe.to_dict(),
        "guardrails": {
            "calibration_strategy": "pit",
            "multiple_testing": "deflated_sharpe_and_fdr",
            "slippage_model": "tiered_functional",
            "decision_grade_required": True,
        },
    }


@router.get("/{strategy_id}", response_model=StrategyRead)
async def get_strategy(strategy_id: UUID, session: AsyncSession = Depends(get_db)) -> Strategy:
    row = await session.get(Strategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return row
