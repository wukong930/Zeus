"""Forecast lifecycle read API: unit (leg shaping) + integration (live PG endpoints)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.forecast import _forecast_to_dict
from app.core.config import get_settings
from app.core.database import get_db
from app.main import create_app
from app.models.forecast import ForecastRecord


class _Row:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def test_forecast_to_dict_splits_long_short_legs() -> None:
    row = _Row(
        id=uuid.uuid4(),
        as_of=datetime(2024, 1, 10, tzinfo=timezone.utc),
        signal="xs_reversal_mom120",
        model_version="xs_reversal/1.0",
        feature_hash="abc",
        decision_grade=False,
        horizon_days=21,
        universe_size=40,
        target_weights={"RB": 0.1, "HC": 0.1, "CU": -0.1, "AL": -0.1},
        realized_return=None,
        resolved_at=None,
        created_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )
    out = _forecast_to_dict(row)
    assert out["long"] == ["HC", "RB"]  # positive weights (the losers), sorted
    assert out["short"] == ["AL", "CU"]  # negative weights (the winners), sorted
    assert out["decision_grade"] is False
    assert out["realized_return"] is None
    assert out["universe_size"] == 40


def _db_url() -> str:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or get_settings().database_url


@pytest_asyncio.fixture
async def forecast_env():
    engine = create_async_engine(_db_url())
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM forecast_records LIMIT 1"))
    except Exception as exc:  # noqa: BLE001 - unreachable/missing schema => skip
        await engine.dispose()
        pytest.skip(f"no Postgres with forecast_records reachable: {repr(exc)[:100]}")

    session = AsyncSession(engine)
    app = create_app()

    async def _override_db():
        yield session  # endpoints share the test's (uncommitted) transaction

    app.dependency_overrides[get_db] = _override_db
    try:
        yield session, app
    finally:
        app.dependency_overrides.clear()
        await session.rollback()  # never commit
        await session.close()
        await engine.dispose()


@pytest.mark.integration
async def test_forecast_overview_endpoint(forecast_env) -> None:
    session, app = forecast_env
    signal = f"xs_reversal_test_{uuid.uuid4().hex[:8]}"
    base = datetime(2024, 5, 1, tzinfo=timezone.utc)
    session.add_all(
        [
            ForecastRecord(
                as_of=base, signal=signal, model_version="xs_reversal/1.0", feature_hash="h1",
                target_weights={"RB": 0.5, "CU": -0.5}, universe_size=2, decision_grade=False,
                horizon_days=21, realized_return=0.03, resolved_at=base + timedelta(days=21),
            ),
            ForecastRecord(
                as_of=base + timedelta(days=30), signal=signal, model_version="xs_reversal/1.0",
                feature_hash="h2", target_weights={"HC": 0.5, "AL": -0.5}, universe_size=2,
                decision_grade=False, horizon_days=21,
            ),
        ]
    )
    await session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overview = await client.get(f"/api/forecast/overview?signal={signal}")
        assert overview.status_code == 200
        body = overview.json()
        assert body["signal"] == signal
        assert body["promoted"] is False
        assert body["status"] == "shadow"
        assert body["latest"]["long"] == ["HC"]  # the most recent forecast's legs
        assert body["latest"]["short"] == ["AL"]
        assert body["shadow_performance"]["resolved"] == 1  # one realized shadow forecast
        assert body["live"]["periods"] == 0  # nothing is authoritative yet

        history = await client.get(f"/api/forecast/history?signal={signal}&limit=10")
        assert history.status_code == 200
        records = history.json()["records"]
        assert len(records) == 2
        assert records[0]["as_of"] > records[1]["as_of"]  # newest first
