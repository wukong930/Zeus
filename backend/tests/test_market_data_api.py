from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.market_data import (
    _latest_market_data_statement,
    _parse_market_symbols,
    _recent_market_data_statement,
)
from app.core.database import get_db
from app.main import create_app
from app.models.market_data import MarketData


def test_parse_market_symbols_dedupes_and_normalizes() -> None:
    assert _parse_market_symbols(" rb,HC, rb ,,sc ") == ["RB", "HC", "SC"]


def test_parse_market_symbols_rejects_empty_after_normalization() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/market-data/latest?symbols=,,,")

    assert response.status_code == 400
    assert response.json()["detail"] == "symbols must include at least one value"


def test_parse_market_symbols_rejects_too_many_unique_values() -> None:
    app = create_app()
    client = TestClient(app)
    symbols = ",".join(f"S{i}" for i in range(51))

    response = client.get(f"/api/market-data/latest?symbols={symbols}")

    assert response.status_code == 400
    assert "at most 50" in response.json()["detail"]


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

    response = client.get("/api/market-data/latest?symbols=rb,hc,rb")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ["RB", "HC"]}
    assert [row["symbol"] for row in response.json()] == ["RB", "HC"]


def test_recent_market_data_batch_endpoint_returns_requested_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_recent_market_data_for_symbols(db_session, symbols, *, limit):
        captured["session"] = db_session
        captured["symbols"] = symbols
        captured["limit"] = limit
        return [_market_row("RB", days=2), _market_row("RB", days=1), _market_row("HC", days=2)]

    monkeypatch.setattr(
        "app.api.market_data.recent_market_data_for_symbols",
        fake_recent_market_data_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/market-data/recent?symbols=rb,hc,rb&limit=2")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ["RB", "HC"], "limit": 2}
    assert [row["symbol"] for row in response.json()] == ["RB", "RB", "HC"]


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

    response = client.get("/api/market-data/symbols/sc/latest")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ["sc"]}
    assert response.json()["symbol"] == "SC"


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
