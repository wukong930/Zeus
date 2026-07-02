"""Real-Postgres integration tests for point-in-time (PIT) query correctness.

The other PIT tests use a FakeSession and assert on the *compiled SQL* — they
prove the statement is shaped right, but never that it returns the right ROWS.
These run the actual PIT statements against a live Postgres and assert on the
returned rows, which is the only way to verify the two core invariants:

* **PIT visibility / no future leakage** — the ``row_number() OVER (... ORDER BY
  vintage_at DESC)`` picks the latest vintage whose ``vintage_at <= as_of``; an
  earlier ``as_of`` must NOT see a later revision.
* **Keyset pagination** — paging with the 3-key ``(timestamp, contract_month,
  id)`` cursor over rows that share a timestamp loses and duplicates nothing.

Skipped automatically when no Postgres is reachable, so the fast unit suite is
unaffected. Runs locally with ``docker compose up postgres`` (default URL points
at the mapped host port) and in CI via the ``backend-test`` service.

Isolation: each test inserts rows under a unique symbol inside a transaction that
is rolled back on teardown (never committed), so the target database is untouched.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.industry_data import IndustryData
from app.models.market_data import MarketData
from app.services.market_data.pit import get_industry_data_pit, get_market_data_pit

pytestmark = pytest.mark.integration


def _db_url() -> str:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or get_settings().database_url


@pytest_asyncio.fixture
async def pit_session() -> AsyncSession:
    engine = create_async_engine(_db_url())
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM market_data LIMIT 1"))
            await conn.execute(text("SELECT 1 FROM industry_data LIMIT 1"))
    except Exception as exc:  # noqa: BLE001 - unreachable/missing schema => skip, not fail
        await engine.dispose()
        pytest.skip(f"no Postgres with PIT tables reachable: {repr(exc)[:100]}")

    session = AsyncSession(engine)
    try:
        yield session
    finally:
        await session.rollback()  # discard everything; never commit
        await session.close()
        await engine.dispose()


def _unique_symbol() -> str:
    return f"PITTEST_{uuid.uuid4().hex[:12]}"


def _bar(symbol: str, *, contract_month: str, timestamp: datetime, vintage_at: datetime, close: float) -> MarketData:
    return MarketData(
        market="SHFE",
        exchange="SHFE",
        commodity="pit-test",
        symbol=symbol,
        contract_month=contract_month,
        timestamp=timestamp,
        vintage_at=vintage_at,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


async def test_market_data_pit_returns_latest_vintage_visible_as_of(pit_session: AsyncSession) -> None:
    symbol = _unique_symbol()
    ts = datetime(2024, 1, 10, tzinfo=timezone.utc)
    original_vintage = datetime(2024, 1, 10, tzinfo=timezone.utc)
    revised_vintage = datetime(2024, 1, 20, tzinfo=timezone.utc)
    pit_session.add_all(
        [
            _bar(symbol, contract_month="2403", timestamp=ts, vintage_at=original_vintage, close=100.0),
            _bar(symbol, contract_month="2403", timestamp=ts, vintage_at=revised_vintage, close=200.0),
        ]
    )
    await pit_session.flush()  # visible to same-transaction queries; not committed

    # as_of before the revision -> only the original vintage is visible.
    before = await get_market_data_pit(
        pit_session, symbol=symbol, as_of=datetime(2024, 1, 15, tzinfo=timezone.utc)
    )
    assert [row.close for row in before] == [100.0]

    # as_of after the revision -> the latest vintage <= as_of wins.
    after = await get_market_data_pit(
        pit_session, symbol=symbol, as_of=datetime(2024, 1, 25, tzinfo=timezone.utc)
    )
    assert [row.close for row in after] == [200.0]

    # no as_of -> the latest vintage overall.
    latest = await get_market_data_pit(pit_session, symbol=symbol)
    assert [row.close for row in latest] == [200.0]


async def test_market_data_pit_as_of_before_first_vintage_sees_nothing(pit_session: AsyncSession) -> None:
    symbol = _unique_symbol()
    ts = datetime(2024, 1, 10, tzinfo=timezone.utc)
    pit_session.add(
        _bar(symbol, contract_month="2403", timestamp=ts, vintage_at=datetime(2024, 1, 10, tzinfo=timezone.utc), close=100.0)
    )
    await pit_session.flush()

    # Knowledge cutoff before the row was ever recorded -> no leakage.
    rows = await get_market_data_pit(
        pit_session, symbol=symbol, as_of=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    assert rows == []


async def test_market_data_keyset_pagination_no_dupes_or_gaps(pit_session: AsyncSession) -> None:
    symbol = _unique_symbol()
    base = datetime(2024, 2, 1, tzinfo=timezone.utc)
    # 3 timestamps x 2 contract months = 6 rows; ties on timestamp exercise the
    # middle sort key that a naive 2-key cursor would skip.
    to_add = [
        _bar(symbol, contract_month=cm, timestamp=base + timedelta(days=day), vintage_at=base + timedelta(days=day), close=100.0 + day)
        for day in range(3)
        for cm in ("2403", "2406")
    ]
    pit_session.add_all(to_add)
    await pit_session.flush()

    full = await get_market_data_pit(pit_session, symbol=symbol, limit=100)
    assert len(full) == 6

    paged: list[MarketData] = []
    cursor: dict = {}
    for _ in range(10):  # generous bound; real loop breaks below
        page = await get_market_data_pit(pit_session, symbol=symbol, limit=2, **cursor)
        if not page:
            break
        paged.extend(page)
        last = page[-1]
        cursor = {
            "before": last.timestamp,
            "before_contract_month": last.contract_month,
            "before_id": last.id,
        }
        if len(page) < 2:
            break

    # Paging reproduces the full ordered result exactly: no dupes, no gaps.
    assert [row.id for row in paged] == [row.id for row in full]
    assert len({row.id for row in paged}) == 6


async def test_industry_data_pit_visibility(pit_session: AsyncSession) -> None:
    symbol = _unique_symbol()
    ts = datetime(2024, 3, 1, tzinfo=timezone.utc)
    pit_session.add_all(
        [
            IndustryData(
                symbol=symbol, data_type="inventory", value=10.0, unit="t", source="pit-test",
                timestamp=ts, vintage_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            ),
            IndustryData(
                symbol=symbol, data_type="inventory", value=20.0, unit="t", source="pit-test",
                timestamp=ts, vintage_at=datetime(2024, 3, 10, tzinfo=timezone.utc),
            ),
        ]
    )
    await pit_session.flush()

    before = await get_industry_data_pit(
        pit_session, symbol=symbol, as_of=datetime(2024, 3, 5, tzinfo=timezone.utc)
    )
    assert [row.value for row in before] == [10.0]

    after = await get_industry_data_pit(
        pit_session, symbol=symbol, as_of=datetime(2024, 3, 15, tzinfo=timezone.utc)
    )
    assert [row.value for row in after] == [20.0]
