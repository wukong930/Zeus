from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from app.models.market_data import MarketData
from app.services.risk.correlation import build_correlation_matrix
from app.services.risk.market_data import _risk_market_data_statement, load_risk_market_data
from app.services.risk.stress import StressScenario, extract_historical_extremes, run_stress_test
from app.services.risk.types import RiskLeg, RiskMarketPoint, RiskPosition
from app.services.risk.var import calculate_var


def _market_data(symbol: str, closes: list[float]) -> list[RiskMarketPoint]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        RiskMarketPoint(symbol=symbol, timestamp=start + timedelta(days=idx), close=close)
        for idx, close in enumerate(closes)
    ]


def _position(*, status: str = "open", legs: tuple[RiskLeg, ...] | None = None) -> RiskPosition:
    return RiskPosition(
        id="p1",
        strategy_name="test",
        status=status,
        legs=legs
        or (
            RiskLeg(
                asset="RB2506",
                direction="long",
                size=10,
                current_price=3500,
            ),
        ),
    )


class FakeScalars:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.scalars_count = 0
        self.statement = None

    async def scalars(self, statement):
        self.scalars_count += 1
        self.statement = statement
        return FakeScalars(self.rows)


def test_calculate_var_returns_zero_for_empty_positions() -> None:
    result = calculate_var([], {})

    assert result.var95 == 0
    assert result.var99 == 0
    assert result.cvar95 == 0
    assert result.cvar99 == 0


async def test_load_risk_market_data_batches_symbols_and_preserves_empty_keys() -> None:
    rows = [
        _market_row("RB2506", close=3500, days=2),
        _market_row("RB2506", close=3490, days=1),
        _market_row("HC2506", close=3410, days=2),
    ]
    session = FakeSession(rows)

    result = await load_risk_market_data(
        session,  # type: ignore[arg-type]
        ["RB2506", "HC2506", "MISSING"],
        limit=60,
    )

    assert set(result) == {"RB2506", "HC2506", "MISSING"}
    assert [point.close for point in result["RB2506"]] == [3500, 3490]
    assert [point.close for point in result["HC2506"]] == [3410]
    assert result["MISSING"] == []
    assert session.scalars_count == 1


def test_risk_market_data_statement_limits_rows_per_symbol() -> None:
    compiled = str(
        _risk_market_data_statement(requested_symbols=("RB2506", "HC2506"), limit=60).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "row_number() OVER" in compiled
    assert "PARTITION BY market_data.symbol, market_data.contract_month, market_data.timestamp" in compiled
    assert "PARTITION BY market_data.symbol ORDER BY market_data.timestamp DESC" in compiled
    assert "symbol_rn <= 60" in compiled


def test_calculate_var_uses_loss_semantics_for_open_position() -> None:
    closes = [3500 + (-1) ** idx * idx * 4 for idx in range(60)]
    result = calculate_var([_position()], {"RB2506": _market_data("RB2506", closes)})

    assert result.var95 < 0
    assert result.var99 <= result.var95
    assert result.cvar95 <= result.var95


def test_calculate_var_returns_zero_for_flat_prices() -> None:
    result = calculate_var(
        [_position()],
        {"RB2506": _market_data("RB2506", [3500] * 50)},
    )

    assert result.var95 == 0
    assert result.var99 == 0


def test_stress_test_computes_long_and_short_impacts() -> None:
    positions = [
        RiskPosition(
            id="hedge1",
            strategy_name="hedge",
            legs=(
                RiskLeg(asset="RB2501", direction="long", current_price=4000, size=10),
                RiskLeg(asset="HC2501", direction="short", current_price=3800, size=10),
            ),
        )
    ]

    results = run_stress_test(
        positions,
        [StressScenario(name="test", description="test scenario", shocks={"RB": -0.2, "HC": -0.2})],
    )

    assert results[0].portfolio_pnl == -400
    assert results[0].position_impacts[0].pnl == -400


def test_stress_test_skips_closed_positions() -> None:
    results = run_stress_test(
        [_position(status="closed")],
        [StressScenario(name="test", description="test scenario", shocks={"RB": -0.2})],
    )

    assert results[0].portfolio_pnl == 0
    assert results[0].position_impacts == ()


def test_extract_historical_extremes_builds_tail_adjusted_scenario() -> None:
    closes = [100] * 30 + [200]
    scenarios = extract_historical_extremes({"RB2501": _market_data("RB2501", closes)})

    assert len(scenarios) >= 1
    assert scenarios[0].historical is True
    assert scenarios[0].shocks["RB"] == 1.3


def test_correlation_matrix_detects_inverse_relationship() -> None:
    rb = _market_data("RB2506", [100, 110, 99, 108.9, 98.01, 107.811])
    hc = _market_data("HC2506", [100, 90, 99, 89.1, 98.01, 88.209])

    result = build_correlation_matrix(
        {"RB2506": rb, "HC2506": hc},
        ["RB2506", "HC2506"],
        window=5,
    )

    assert result.symbols == ("RB2506", "HC2506")
    assert result.matrix[0][0] == 1
    assert result.matrix[1][1] == 1
    assert result.matrix[0][1] < -0.99
    assert result.matrix[1][0] < -0.99


def test_var_api_marks_insufficient_market_data_degraded(monkeypatch) -> None:
    client = _risk_api_client(
        monkeypatch,
        positions=[_position()],
        market_data={"RB2506": _market_data("RB2506", [3500, 3510, 3495])},
    )

    response = client.get("/api/risk/var")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["degraded"] is True
    assert payload["unavailable_sections"] == ["market_data_insufficient:RB2506"]
    assert payload["data"]["var95"] == 0


def test_var_api_keeps_empty_portfolio_non_degraded(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.get("/api/risk/var")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["degraded"] is False
    assert payload["unavailable_sections"] == []


def test_stress_api_marks_symbols_without_scenario_coverage(monkeypatch) -> None:
    client = _risk_api_client(
        monkeypatch,
        positions=[
            _position(
                legs=(
                    RiskLeg(asset="NR2509", direction="long", current_price=12000, size=2),
                )
            )
        ],
        market_data={},
    )

    response = client.get("/api/risk/stress")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["degraded"] is True
    assert payload["unavailable_sections"] == ["stress_uncovered_symbols:NR2509"]


def test_custom_stress_api_normalizes_shock_symbols(monkeypatch) -> None:
    client = _risk_api_client(
        monkeypatch,
        positions=[_position()],
        market_data={},
    )

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "rb pullback",
                    "description": "lowercase contract shock should match RB legs",
                    "shocks": {"rb2506": -0.1},
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["portfolio_pnl"] == -3500
    assert payload["degraded"] is False


def test_custom_stress_api_rejects_empty_scenarios(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post("/api/risk/stress", json={"scenarios": []})

    assert response.status_code == 422


def test_custom_stress_api_rejects_too_many_scenarios(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})
    scenarios = [
        {"name": f"s{i}", "description": "shock", "shocks": {"RB": -0.01}}
        for i in range(21)
    ]

    response = client.post("/api/risk/stress", json={"scenarios": scenarios})

    assert response.status_code == 422


def test_custom_stress_api_rejects_too_many_shocks(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "wide shock",
                    "description": "too many shocked symbols",
                    "shocks": {f"S{i}": -0.01 for i in range(41)},
                }
            ]
        },
    )

    assert response.status_code == 422


def test_custom_stress_api_rejects_unbounded_shock(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "bad shock",
                    "description": "outside stress bounds",
                    "shocks": {"RB": -1.5},
                }
            ]
        },
    )

    assert response.status_code == 422


def test_custom_stress_api_rejects_blank_scenario_text(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "   ",
                    "description": "blank names should not reach risk calculation",
                    "shocks": {"RB": -0.1},
                }
            ]
        },
    )

    assert response.status_code == 422


def test_custom_stress_api_rejects_string_historical_flag(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "rb shock",
                    "description": "historical must be a JSON boolean",
                    "shocks": {"RB": -0.1},
                    "historical": "false",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_custom_stress_api_rejects_oversized_shock_symbol(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.post(
        "/api/risk/stress",
        json={
            "scenarios": [
                {
                    "name": "wide symbol",
                    "description": "shock symbol is too long",
                    "shocks": {"X" * 33: -0.1},
                }
            ]
        },
    )

    assert response.status_code == 422


def test_correlation_api_marks_missing_series_degraded(monkeypatch) -> None:
    client = _risk_api_client(
        monkeypatch,
        positions=[],
        market_data={
            "RB2506": _market_data("RB2506", [3500, 3510, 3490, 3520]),
            "HC2506": [],
        },
    )

    response = client.get("/api/risk/correlation?symbols=RB2506,HC2506&window=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["degraded"] is True
    assert payload["unavailable_sections"] == ["correlation_data_missing:HC2506"]


def test_correlation_api_normalizes_and_dedupes_symbols(monkeypatch) -> None:
    captured: dict[str, object] = {}
    client = _risk_api_client(
        monkeypatch,
        positions=[],
        market_data={
            "RB2506": _market_data("RB2506", [3500, 3510, 3490, 3520]),
            "HC2506": _market_data("HC2506", [3400, 3420, 3390, 3430]),
        },
        captured=captured,
    )

    response = client.get("/api/risk/correlation?symbols=rb2506,HC2506,rb2506&window=5")

    assert response.status_code == 200
    assert captured["symbols"] == ["RB2506", "HC2506"]


def test_correlation_api_rejects_empty_symbol_query(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.get("/api/risk/correlation?symbols=,,,&window=5")

    assert response.status_code == 400
    assert response.json()["detail"] == "symbols must include at least one value"


def test_correlation_api_rejects_too_many_symbols(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})
    symbols = ",".join(f"S{i}" for i in range(41))

    response = client.get(f"/api/risk/correlation?symbols={symbols}&window=5")

    assert response.status_code == 400
    assert "at most 40" in response.json()["detail"]


def test_correlation_api_rejects_oversized_symbol(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})

    response = client.get(f"/api/risk/correlation?symbols={'X' * 33}&window=5")

    assert response.status_code == 400
    assert "at most 32" in response.json()["detail"]


def test_correlation_api_rejects_oversized_symbol_query(monkeypatch) -> None:
    client = _risk_api_client(monkeypatch, positions=[], market_data={})
    symbols = ",".join("RB" for _ in range(600))

    response = client.get(f"/api/risk/correlation?symbols={symbols}&window=5")

    assert response.status_code == 422


def _risk_api_client(
    monkeypatch,
    *,
    positions: list[RiskPosition],
    market_data: dict,
    captured: dict[str, object] | None = None,
):
    async def fake_db():
        yield object()

    async def fake_open_positions(_session):
        return positions

    async def fake_load_risk_market_data(_session, symbols, *, limit):
        if captured is not None:
            captured["symbols"] = symbols
            captured["limit"] = limit
        return {symbol: list(market_data.get(symbol, [])) for symbol in symbols}

    monkeypatch.setattr("app.api.risk._open_positions", fake_open_positions)
    monkeypatch.setattr("app.api.risk.load_risk_market_data", fake_load_risk_market_data)

    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def _market_row(symbol: str, *, close: float, days: int) -> MarketData:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days)
    return MarketData(
        source_key=None,
        market="CN",
        exchange="SHFE",
        commodity=symbol,
        symbol=symbol,
        contract_month=symbol[-4:],
        timestamp=timestamp,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=1000,
        vintage_at=timestamp,
        ingested_at=timestamp,
    )
