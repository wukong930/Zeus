from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.recommendation import Recommendation
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
    status_filter: str | None = Query(default=None, max_length=20),
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
    outcomes = await load_runtime_recommendation_outcomes(session)
    returns = [item["return_pct"] for item in outcomes]
    observations = [
        RegimeObservation(str(item["regime"] or "unknown"), item["return_pct"])
        for item in outcomes
    ]
    degraded_reasons = []
    if not returns:
        degraded_reasons.append("no_completed_recommendation_outcomes")
    elif len(returns) < 5:
        degraded_reasons.append("insufficient_completed_recommendation_outcomes")
    if not universe.valid:
        degraded_reasons.append("invalid_point_in_time_universe")
    return {
        "as_of": effective_as_of.isoformat(),
        "source": "runtime_recommendations",
        "sample_size": len(returns),
        "degraded": bool(degraded_reasons),
        "unavailable_sections": degraded_reasons,
        "walk_forward": walk_forward_defaults(),
        "regime_profile": [item.to_dict() for item in build_regime_profile(observations)],
        "path_metrics": calculate_path_metrics(
            returns,
            mae_values=[
                item["mae_pct"]
                for item in outcomes
                if item["mae_pct"] is not None
            ],
            mfe_values=[
                item["mfe_pct"]
                for item in outcomes
                if item["mfe_pct"] is not None
            ],
        ).to_dict(),
        "universe": universe.to_dict(),
        "guardrails": {
            "calibration_strategy": "pit",
            "multiple_testing": "deflated_sharpe_and_fdr",
            "slippage_model": "tiered_functional",
            "decision_grade_required": True,
        },
    }


async def load_runtime_recommendation_outcomes(
    session: AsyncSession,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(Recommendation)
            .where(
                or_(
                    Recommendation.status == "completed",
                    Recommendation.pnl_realized.is_not(None),
                    Recommendation.actual_exit.is_not(None),
                )
            )
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
        )
    ).all()
    outcomes = [recommendation_outcome(row) for row in rows]
    return [item for item in outcomes if item is not None]


def recommendation_outcome(row: Recommendation) -> dict[str, Any] | None:
    entry = positive_float(row.actual_entry, row.entry_price)
    exit_value = positive_float(row.actual_exit)
    if entry is not None and exit_value is not None:
        direction = primary_recommendation_direction(row)
        move = exit_value - entry
        signed_move = -move if direction == "short" else move
        return_pct = signed_move / abs(entry)
    elif row.pnl_realized is not None and row.margin_required:
        return_pct = float(row.pnl_realized) / abs(float(row.margin_required))
    else:
        return None

    return {
        "return_pct": return_pct,
        "regime": recommendation_regime(row),
        "mae_pct": excursion_pct(row.mae, entry),
        "mfe_pct": excursion_pct(row.mfe, entry),
    }


def recommendation_regime(row: Recommendation) -> str:
    summary = row.backtest_summary or {}
    for key in ("regime", "market_regime", "state"):
        value = summary.get(key)
        if value:
            return str(value)
    return "unknown"


def primary_recommendation_direction(row: Recommendation) -> str:
    for leg in row.legs or []:
        if not isinstance(leg, dict):
            continue
        direction = str(leg.get("direction") or "long").lower()
        if direction in {"short", "sell"}:
            return "short"
        if direction in {"long", "buy"}:
            return "long"
    return "long"


def positive_float(*values: float | None) -> float | None:
    for value in values:
        if value is None:
            continue
        number = float(value)
        if number > 0:
            return number
    return None


def excursion_pct(value: float | None, entry: float | None) -> float | None:
    if value is None or entry is None or entry == 0:
        return None
    return float(value) / abs(entry)


@router.get("/{strategy_id}", response_model=StrategyRead)
async def get_strategy(strategy_id: UUID, session: AsyncSession = Depends(get_db)) -> Strategy:
    row = await session.get(Strategy, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return row
