from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.position import Position
from app.models.recommendation import Recommendation


@dataclass(frozen=True)
class AttributionUpdate:
    recommendation_id: str | None
    updated: bool
    status: str | None = None
    pnl_realized: float | None = None


async def update_recommendation_from_position(
    session: AsyncSession,
    position: Position,
    *,
    as_of: datetime | None = None,
) -> AttributionUpdate:
    if position.recommendation_id is None:
        return AttributionUpdate(None, False)
    recommendation = await session.get(Recommendation, position.recommendation_id)
    if recommendation is None:
        return AttributionUpdate(str(position.recommendation_id), False)

    effective_at = as_of or datetime.now(timezone.utc)
    actual_entry = recommendation.actual_entry or position.avg_entry_price or position.entry_spread
    current_value = position.current_spread

    recommendation.actual_entry = actual_entry
    if recommendation.entry_price is None:
        recommendation.entry_price = actual_entry
    recommendation.holding_period_days = holding_period_days(position, effective_at)

    update_excursions(recommendation, position, current_value=current_value)

    if position.status == "closed":
        recommendation.actual_exit = recommendation.actual_exit or current_value
        recommendation.actual_exit_reason = recommendation.actual_exit_reason or (
            position.exit_condition or "manual_close"
        )
        recommendation.pnl_realized = (
            position.realized_pnl
            if position.realized_pnl is not None
            else calculate_position_pnl(
                position,
                actual_entry=actual_entry,
                actual_exit=recommendation.actual_exit,
            )
        )
        recommendation.status = "completed"
    elif recommendation.status == "pending":
        recommendation.status = "accepted"

    await session.flush()
    return AttributionUpdate(
        recommendation_id=str(recommendation.id),
        updated=True,
        status=recommendation.status,
        pnl_realized=recommendation.pnl_realized,
    )


async def update_open_recommendation_excursions(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
) -> int:
    rows = (
        await session.scalars(
            select(Position).where(
                Position.status == "open",
                Position.recommendation_id.is_not(None),
            )
        )
    ).all()
    updated = 0
    for row in rows:
        result = await update_recommendation_from_position(session, row, as_of=as_of)
        if result.updated:
            updated += 1
    return updated


def update_excursions(
    recommendation: Recommendation,
    position: Position,
    *,
    current_value: float,
) -> None:
    entry = recommendation.actual_entry or recommendation.entry_price or position.entry_spread
    signed_move = signed_price_move(position, actual_entry=entry, actual_exit=current_value)
    recommendation.mfe = max(float(recommendation.mfe or 0), max(0.0, signed_move))
    recommendation.mae = min(float(recommendation.mae or 0), min(0.0, signed_move))


def calculate_position_pnl(
    position: Position,
    *,
    actual_entry: float,
    actual_exit: float,
) -> float:
    signed_move = signed_price_move(position, actual_entry=actual_entry, actual_exit=actual_exit)
    size = position_size(position)
    multiplier = contract_multiplier(position)
    return round(signed_move * size * multiplier, 2)


def signed_price_move(position: Position, *, actual_entry: float, actual_exit: float) -> float:
    direction = primary_direction(position)
    move = actual_exit - actual_entry
    return -move if direction == "short" else move


def primary_direction(position: Position) -> str:
    for leg in position.legs or []:
        if isinstance(leg, dict):
            direction = str(leg.get("direction") or "long").lower()
            return "short" if direction == "short" else "long"
    return "long"


def position_size(position: Position) -> float:
    values: list[float] = []
    for leg in position.legs or []:
        if isinstance(leg, dict):
            values.append(float(leg.get("size") or leg.get("quantity") or leg.get("lots") or 0))
    return max(sum(abs(value) for value in values), 1.0)


def contract_multiplier(position: Position) -> float:
    multipliers: list[float] = []
    for leg in position.legs or []:
        if isinstance(leg, dict):
            value = leg.get("contract_multiplier") or leg.get("multiplier")
            if value is not None:
                multipliers.append(float(value))
    if not multipliers:
        return 1.0
    return sum(multipliers) / len(multipliers)


def holding_period_days(position: Position, as_of: datetime) -> float:
    end = position.closed_at or as_of
    return round(max((end - position.opened_at).total_seconds(), 0) / 86400, 4)
