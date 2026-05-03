from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commodity_history import CommodityHistory


@dataclass(frozen=True, slots=True)
class UniverseValidation:
    as_of: date
    requested_symbols: tuple[str, ...]
    active_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_symbols

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "requested_symbols": list(self.requested_symbols),
            "active_symbols": list(self.active_symbols),
            "missing_symbols": list(self.missing_symbols),
            "valid": self.valid,
        }


async def pit_commodity_universe(session: AsyncSession, *, as_of: date) -> list[str]:
    rows = (
        await session.scalars(
            select(CommodityHistory)
            .where(
                CommodityHistory.active_from <= as_of,
                or_(CommodityHistory.active_to.is_(None), CommodityHistory.active_to >= as_of),
            )
            .order_by(CommodityHistory.symbol.asc())
        )
    ).all()
    return [row.symbol for row in rows]


async def validate_backtest_universe(
    session: AsyncSession,
    *,
    symbols: list[str],
    as_of: date,
) -> UniverseValidation:
    requested = tuple(sorted({symbol.upper() for symbol in symbols if symbol.strip()}))
    active = tuple(await pit_commodity_universe(session, as_of=as_of))
    active_set = set(active)
    missing = tuple(symbol for symbol in requested if symbol not in active_set)
    return UniverseValidation(
        as_of=as_of,
        requested_symbols=requested,
        active_symbols=active,
        missing_symbols=missing,
    )


def validate_backtest_universe_from_symbols(
    *,
    symbols: list[str],
    active_symbols: list[str],
    as_of: date,
) -> UniverseValidation:
    requested = tuple(sorted({symbol.upper() for symbol in symbols if symbol.strip()}))
    active = tuple(sorted({symbol.upper() for symbol in active_symbols if symbol.strip()}))
    active_set = set(active)
    return UniverseValidation(
        as_of=as_of,
        requested_symbols=requested,
        active_symbols=active,
        missing_symbols=tuple(symbol for symbol in requested if symbol not in active_set),
    )
