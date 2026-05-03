from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_metadata import ContractMetadata
from app.models.market_data import MarketData
from app.services.contracts.main_contract_detector import (
    ContractCandidate,
    detect_main_contract_switch,
)
from app.services.market_data.pit import get_market_data_pit


@dataclass(frozen=True)
class MainContractRecord:
    symbol: str
    status: str
    contract_month: str | None = None
    reason: str | None = None

    def to_detail(self) -> dict:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "contract_month": self.contract_month,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MainContractBatchResult:
    symbols: int
    updated: int
    skipped: int
    details: list[dict]


def contract_candidate_from_market_data(row: MarketData) -> ContractCandidate:
    return ContractCandidate(
        symbol=row.symbol,
        contract_month=row.contract_month,
        trading_date=row.timestamp.date(),
        volume=row.volume,
        open_interest=row.open_interest or 0,
    )


def latest_contract_snapshots(rows: list[MarketData]) -> dict[str, MarketData]:
    snapshots: dict[str, MarketData] = {}
    for row in sorted(rows, key=lambda item: item.timestamp):
        snapshots[row.contract_month] = row
    return snapshots


async def detect_and_apply_main_contracts(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 10,
    confirmation_days: int = 3,
) -> MainContractBatchResult:
    effective_as_of = as_of or datetime.now(timezone.utc)
    start = effective_as_of - timedelta(days=lookback_days)
    symbols = await _recent_symbols(session, start=start, end=effective_as_of)

    details: list[dict] = []
    updated = 0
    skipped = 0
    for symbol in symbols:
        result = await detect_and_apply_symbol_main_contract(
            session,
            symbol=symbol,
            as_of=effective_as_of,
            start=start,
            confirmation_days=confirmation_days,
        )
        details.append(result.to_detail())
        if result.status == "updated":
            updated += 1
        else:
            skipped += 1

    return MainContractBatchResult(
        symbols=len(symbols),
        updated=updated,
        skipped=skipped,
        details=details,
    )


async def detect_and_apply_symbol_main_contract(
    session: AsyncSession,
    *,
    symbol: str,
    as_of: datetime,
    start: datetime,
    confirmation_days: int = 3,
) -> MainContractRecord:
    rows = await get_market_data_pit(
        session,
        symbol=symbol,
        as_of=as_of,
        start=start,
        end=as_of,
        limit=5000,
    )
    if not rows:
        return MainContractRecord(symbol=symbol, status="skipped", reason="no_market_data")

    for snapshot in latest_contract_snapshots(rows).values():
        await upsert_contract_metadata(session, snapshot)

    current = await get_current_main_contract(session, symbol=symbol)
    switch = detect_main_contract_switch(
        [contract_candidate_from_market_data(row) for row in rows],
        current_contract_month=current.contract_month if current is not None else None,
        confirmation_days=confirmation_days,
    )
    if switch is None:
        return MainContractRecord(
            symbol=symbol,
            status="skipped",
            contract_month=current.contract_month if current is not None else None,
            reason="no_confirmed_switch",
        )

    await apply_main_contract_switch(
        session,
        symbol=symbol,
        contract_month=switch.contract_month,
        as_of=as_of,
        volume=switch.volume,
        open_interest=switch.open_interest,
    )
    return MainContractRecord(
        symbol=symbol,
        status="updated",
        contract_month=switch.contract_month,
    )


async def get_current_main_contract(
    session: AsyncSession,
    *,
    symbol: str,
) -> ContractMetadata | None:
    return (
        await session.scalars(
            select(ContractMetadata)
            .where(
                ContractMetadata.symbol == symbol,
                ContractMetadata.is_main.is_(True),
                ContractMetadata.main_until.is_(None),
            )
            .limit(1)
        )
    ).first()


async def upsert_contract_metadata(
    session: AsyncSession,
    market_row: MarketData,
) -> ContractMetadata:
    row = (
        await session.scalars(
            select(ContractMetadata)
            .where(
                ContractMetadata.symbol == market_row.symbol,
                ContractMetadata.contract_month == market_row.contract_month,
            )
            .limit(1)
        )
    ).first()
    if row is None:
        row = ContractMetadata(
            symbol=market_row.symbol,
            exchange=market_row.exchange,
            commodity=market_row.commodity,
            contract_month=market_row.contract_month,
        )
        session.add(row)

    row.exchange = market_row.exchange
    row.commodity = market_row.commodity
    row.volume = market_row.volume
    row.open_interest = market_row.open_interest
    await session.flush()
    return row


async def apply_main_contract_switch(
    session: AsyncSession,
    *,
    symbol: str,
    contract_month: str,
    as_of: datetime,
    volume: float,
    open_interest: float,
) -> ContractMetadata:
    current_rows = (
        await session.scalars(
            select(ContractMetadata).where(
                ContractMetadata.symbol == symbol,
                ContractMetadata.is_main.is_(True),
                ContractMetadata.main_until.is_(None),
            )
        )
    ).all()
    for row in current_rows:
        row.is_main = False
        row.main_until = as_of

    target = (
        await session.scalars(
            select(ContractMetadata)
            .where(
                ContractMetadata.symbol == symbol,
                ContractMetadata.contract_month == contract_month,
            )
            .limit(1)
        )
    ).first()
    if target is None:
        target = ContractMetadata(symbol=symbol, contract_month=contract_month)
        session.add(target)

    target.is_main = True
    target.main_from = as_of
    target.main_until = None
    target.volume = volume
    target.open_interest = open_interest
    await session.flush()
    return target


async def _recent_symbols(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
) -> list[str]:
    rows = (
        await session.scalars(
            select(MarketData.symbol)
            .where(MarketData.timestamp >= start, MarketData.timestamp <= end)
            .distinct()
            .order_by(MarketData.symbol.asc())
        )
    ).all()
    return [str(row) for row in rows]
