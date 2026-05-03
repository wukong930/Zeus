from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist import Watchlist


@dataclass(frozen=True)
class WatchlistEntry:
    symbol1: str
    category: str
    symbol2: str | None = None
    priority: int = 100
    custom_thresholds: dict | None = None
    position_linked: bool = False

    @property
    def symbols(self) -> tuple[str, ...]:
        if self.symbol2 is None:
            return (self.symbol1,)
        return (self.symbol1, self.symbol2)

    @property
    def key(self) -> str:
        return ":".join((*self.symbols, self.category))


def normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    value = symbol.strip().upper()
    return value or None


def build_watchlist_query(
    *,
    category: str | None = None,
    include_disabled: bool = False,
    limit: int | None = None,
) -> Select[tuple[Watchlist]]:
    statement = select(Watchlist).order_by(Watchlist.priority.asc(), Watchlist.symbol1.asc())
    if not include_disabled:
        statement = statement.where(Watchlist.enabled.is_(True))
    if category is not None:
        statement = statement.where(Watchlist.category == category)
    if limit is not None:
        statement = statement.limit(limit)
    return statement


def to_watchlist_entry(row: Watchlist) -> WatchlistEntry:
    return WatchlistEntry(
        symbol1=row.symbol1,
        symbol2=row.symbol2,
        category=row.category,
        priority=row.priority,
        custom_thresholds=row.custom_thresholds,
        position_linked=row.position_linked,
    )


async def get_enabled_watchlist(
    session: AsyncSession,
    *,
    category: str | None = None,
    limit: int | None = None,
) -> list[WatchlistEntry]:
    rows = (
        await session.scalars(
            build_watchlist_query(category=category, include_disabled=False, limit=limit)
        )
    ).all()
    return [to_watchlist_entry(row) for row in rows]


async def upsert_position_watchlist_entry(
    session: AsyncSession,
    *,
    symbol1: str,
    category: str,
    symbol2: str | None = None,
    custom_thresholds: dict | None = None,
) -> Watchlist:
    normalized_symbol1 = normalize_symbol(symbol1)
    normalized_symbol2 = normalize_symbol(symbol2)
    if normalized_symbol1 is None:
        raise ValueError("symbol1 is required")

    statement = select(Watchlist).where(
        Watchlist.symbol1 == normalized_symbol1,
        Watchlist.symbol2.is_(None)
        if normalized_symbol2 is None
        else Watchlist.symbol2 == normalized_symbol2,
        Watchlist.category == category,
    )
    row = (await session.scalars(statement.limit(1))).first()
    if row is None:
        row = Watchlist(
            symbol1=normalized_symbol1,
            symbol2=normalized_symbol2,
            category=category,
            priority=10,
            custom_thresholds=custom_thresholds or {},
            position_linked=True,
        )
        session.add(row)
    else:
        row.enabled = True
        row.position_linked = True
        if custom_thresholds is not None:
            row.custom_thresholds = custom_thresholds

    await session.flush()
    return row
