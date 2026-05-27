from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.market_data import (
    _clear_market_data_cache,
    _latest_market_data_statement,
    _parse_market_symbols,
    _recent_market_data_statement,
)
from app.core.database import get_db
from app.main import create_app
from app.models.market_data import MarketData


@pytest.fixture(autouse=True)
def clear_market_data_cache_between_tests():
    _clear_market_data_cache()
    yield
    _clear_market_data_cache()


def test_parse_market_symbols_dedupes_and_normalizes() -> None:
    assert _parse_market_symbols(" rb2509,HC2601, rb ,,sc ") == ["RB", "HC", "SC"]


def test_parse_market_symbols_rejects_empty_after_normalization() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/market-data/latest?symbols=,,,")

    assert response.status_code == 400
    assert response.json()["detail"] == "symbols must include at least one value"


def test_parse_market_symbols_rejects_too_many_unique_values() -> None:
    app = create_app()
    client = TestClient(app)
    symbols = ",".join(f"S{chr(65 + index // 26)}{chr(65 + index % 26)}" for index in range(51))

    response = client.get(f"/api/market-data/latest?symbols={symbols}")

    assert response.status_code == 400
    assert "at most 50" in response.json()["detail"]


def test_parse_market_symbols_rejects_oversized_symbol() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get(f"/api/market-data/latest?symbols={'X' * 33}")

    assert response.status_code == 400
    assert "at most 32" in response.json()["detail"]


def test_market_data_batch_endpoints_reject_oversized_query() -> None:
    app = create_app()
    client = TestClient(app)
    symbols = ",".join("RB" for _ in range(900))

    latest_response = client.get(f"/api/market-data/latest?symbols={symbols}")
    recent_response = client.get(f"/api/market-data/recent?symbols={symbols}")

    assert latest_response.status_code == 422
    assert recent_response.status_code == 422


def test_single_market_data_symbol_inputs_are_bounded() -> None:
    app = create_app()
    client = TestClient(app)

    list_response = client.get(f"/api/market-data?symbol={'X' * 33}")
    latest_response = client.get(f"/api/market-data/symbols/{'X' * 33}/latest")

    assert list_response.status_code == 422
    assert latest_response.status_code == 422


def test_latest_market_data_statement_uses_window_per_symbol() -> None:
    compiled = str(
        _latest_market_data_statement(["RB", "HC"]).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "row_number() OVER" in compiled
    assert "PARTITION BY market_data.symbol" in compiled
    assert "ORDER BY market_data.timestamp DESC" in compiled
    assert "CASE WHEN (market_data.contract_month = 'main')" in compiled
    assert "market_data.symbol IN ('RB', 'HC')" in compiled


def test_recent_market_data_statement_limits_rows_per_symbol() -> None:
    compiled = str(
        _recent_market_data_statement(["RB", "HC"], 5).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "row_number() OVER" in compiled
    assert "PARTITION BY market_data.symbol, market_data.timestamp" in compiled
    assert "ORDER BY anon_" in compiled
    assert ".timestamp DESC" in compiled
    assert "symbol_row_number <= 5" in compiled


def test_recent_market_data_statement_applies_cursor_and_stable_order() -> None:
    before = datetime(2026, 5, 18, tzinfo=timezone.utc)
    compiled = str(
        _recent_market_data_statement(["RB"], 3, before=before).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "market_data.timestamp < '2026-05-18" in compiled
    assert ".timestamp DESC, anon_" in compiled
    assert "ORDER BY market_data.symbol ASC, market_data.timestamp DESC, market_data.id DESC" in compiled


def test_recent_market_data_batch_endpoint_rejects_invalid_cursor() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/market-data/recent?symbols=RB&before=not-a-date")

    assert response.status_code == 422


def test_latest_market_data_batch_endpoint_returns_requested_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_latest_market_data_for_symbols(db_session, symbols):
        captured["session"] = db_session
        captured["symbols"] = symbols
        return [_market_row("RB", days=2), _market_row("HC", days=1)]

    monkeypatch.setattr(
        "app.api.market_data.latest_market_data_for_symbols",
        fake_latest_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/market-data/latest?symbols=rb2509,hc2601,rb")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ["RB", "HC"]}
    assert [row["symbol"] for row in response.json()] == ["RB", "HC"]


def test_recent_market_data_batch_endpoint_returns_requested_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_recent_market_data_for_symbols(db_session, symbols, *, before, limit):
        captured["session"] = db_session
        captured["symbols"] = symbols
        captured["before"] = before
        captured["limit"] = limit
        return [_market_row("RB", days=2), _market_row("RB", days=1), _market_row("HC", days=2)]

    monkeypatch.setattr(
        "app.api.market_data.recent_market_data_for_symbols",
        fake_recent_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/market-data/recent?symbols=rb2509,hc2601,rb&limit=2&before=2026-05-18T00:00:00Z")

    assert response.status_code == 200
    assert captured == {
        "session": session,
        "symbols": ["RB", "HC"],
        "before": datetime(2026, 5, 18, tzinfo=timezone.utc),
        "limit": 2,
    }
    assert [row["symbol"] for row in response.json()] == ["RB", "RB", "HC"]


def test_latest_market_data_batch_endpoint_uses_short_ttl_cache(monkeypatch) -> None:
    calls = {"count": 0}
    session = object()

    async def fake_db():
        yield session

    async def fake_latest_market_data_for_symbols(db_session, symbols):
        calls["count"] += 1
        assert db_session is session
        assert symbols == ["RB", "HC"]
        return [_market_row("RB", days=calls["count"]), _market_row("HC", days=calls["count"])]

    monkeypatch.setattr(
        "app.api.market_data.latest_market_data_for_symbols",
        fake_latest_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    first = client.get("/api/market-data/latest?symbols=rb,hc")
    second = client.get("/api/market-data/latest?symbols=rb,hc")
    refreshed = client.get("/api/market-data/latest?symbols=rb,hc&refresh=true")

    assert first.status_code == 200
    assert second.status_code == 200
    assert refreshed.status_code == 200
    assert calls["count"] == 2
    assert first.json() == second.json()
    assert refreshed.json()[0]["close"] != first.json()[0]["close"]


def test_recent_market_data_batch_endpoint_uses_limit_sensitive_cache(monkeypatch) -> None:
    calls = {"count": 0}
    session = object()

    async def fake_db():
        yield session

    async def fake_recent_market_data_for_symbols(db_session, symbols, *, before, limit):
        calls["count"] += 1
        assert db_session is session
        assert symbols == ["RB"]
        assert before in {None, datetime(2026, 5, 18, tzinfo=timezone.utc)}
        return [_market_row("RB", days=calls["count"])]

    monkeypatch.setattr(
        "app.api.market_data.recent_market_data_for_symbols",
        fake_recent_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    first = client.get("/api/market-data/recent?symbols=rb&limit=2")
    second = client.get("/api/market-data/recent?symbols=rb&limit=2")
    different_limit = client.get("/api/market-data/recent?symbols=rb&limit=3")
    different_cursor = client.get(
        "/api/market-data/recent?symbols=rb&limit=2&before=2026-05-18T00:00:00Z"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert different_limit.status_code == 200
    assert different_cursor.status_code == 200
    assert calls["count"] == 3
    assert first.json() == second.json()
    assert different_limit.json()[0]["close"] != first.json()[0]["close"]
    assert different_cursor.json()[0]["close"] != first.json()[0]["close"]


def test_single_latest_market_data_endpoint_uses_shared_lookup(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_latest_market_data_for_symbols(db_session, symbols):
        captured["session"] = db_session
        captured["symbols"] = symbols
        return [_market_row("SC", days=3)]

    monkeypatch.setattr(
        "app.api.market_data.latest_market_data_for_symbols",
        fake_latest_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/market-data/symbols/sc2509/latest")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ["SC"]}
    assert response.json()["symbol"] == "SC"


def test_market_data_pit_endpoint_normalizes_contract_symbol(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_get_market_data_pit(db_session, *, symbol, as_of, start, end, limit):
        captured["session"] = db_session
        captured["symbol"] = symbol
        captured["limit"] = limit
        return []

    monkeypatch.setattr("app.api.market_data.get_market_data_pit", fake_get_market_data_pit)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/market-data?symbol=sc2509&limit=10")

    assert response.status_code == 200
    assert captured == {"session": session, "symbol": "SC", "limit": 10}


def _market_row(symbol: str, *, days: int) -> MarketData:
    timestamp = datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(days=days)
    return MarketData(
        id=uuid4(),
        source_key=f"{symbol}:{days}",
        market="CN",
        exchange="SHFE",
        commodity=symbol,
        symbol=symbol,
        contract_month="main",
        timestamp=timestamp,
        open=100,
        high=105,
        low=95,
        close=102 + days,
        settle=102 + days,
        volume=1000,
        open_interest=2000,
        currency="CNY",
        timezone="Asia/Shanghai",
        vintage_at=timestamp,
        ingested_at=timestamp,
    )
