from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.position import Position
from app.services.signals.thresholds import ThresholdProfile, get_thresholds

POSITION_THRESHOLD_MULTIPLIER = 0.8
_SENSITIVE_FIELDS = ("z_score_entry", "basis_deviation", "min_confidence")


@dataclass(frozen=True)
class PositionThresholdState:
    position_id: UUID
    symbol: str
    multiplier: float
    monitoring_priority: int


_POSITION_THRESHOLD_CACHE: dict[str, PositionThresholdState] = {}


def normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    value = symbol.strip().upper()
    return value or None


def symbols_from_position(position: Position) -> set[str]:
    symbols: set[str] = set()
    for leg in position.legs or []:
        if not isinstance(leg, dict):
            continue
        symbol = normalize_symbol(str(leg.get("asset") or leg.get("symbol") or ""))
        if symbol:
            symbols.add(symbol)
    return symbols


async def refresh_position_threshold_cache(session: AsyncSession) -> dict[str, PositionThresholdState]:
    rows = (
        await session.scalars(
            select(Position)
            .where(Position.status == "open", Position.data_mode == "position_aware")
            .order_by(Position.monitoring_priority.asc())
        )
    ).all()
    _POSITION_THRESHOLD_CACHE.clear()
    for row in rows:
        update_position_threshold_cache(row)
    return dict(_POSITION_THRESHOLD_CACHE)


def update_position_threshold_cache(position: Position) -> dict[str, PositionThresholdState]:
    for symbol, state in list(_POSITION_THRESHOLD_CACHE.items()):
        if state.position_id == position.id:
            _POSITION_THRESHOLD_CACHE.pop(symbol, None)

    if position.status != "open" or position.data_mode != "position_aware":
        return dict(_POSITION_THRESHOLD_CACHE)

    for symbol in symbols_from_position(position):
        _POSITION_THRESHOLD_CACHE[symbol] = PositionThresholdState(
            position_id=position.id,
            symbol=symbol,
            multiplier=POSITION_THRESHOLD_MULTIPLIER,
            monitoring_priority=position.monitoring_priority,
        )
    return dict(_POSITION_THRESHOLD_CACHE)


def get_position_threshold_multiplier(symbols: list[str] | tuple[str, ...] | set[str]) -> float:
    normalized = {symbol for item in symbols if (symbol := normalize_symbol(str(item)))}
    if not normalized:
        return 1.0
    matches = [
        state.multiplier
        for symbol, state in _POSITION_THRESHOLD_CACHE.items()
        if symbol in normalized
    ]
    return min(matches) if matches else 1.0


def apply_position_threshold_multiplier(
    profile: ThresholdProfile,
    *,
    multiplier: float,
) -> ThresholdProfile:
    if multiplier >= 1:
        return profile
    values = {
        field: max(0.01, getattr(profile, field) * multiplier)
        for field in _SENSITIVE_FIELDS
    }
    return replace(profile, **values)


def get_position_aware_thresholds(
    category: str,
    *,
    symbols: list[str] | tuple[str, ...] | set[str],
    volatility_regime: str = "normal",
    half_life: float | None = None,
) -> ThresholdProfile:
    base = get_thresholds(
        category,
        volatility_regime=volatility_regime,
        half_life=half_life,
    )
    multiplier = get_position_threshold_multiplier(symbols)
    return apply_position_threshold_multiplier(base, multiplier=multiplier)
