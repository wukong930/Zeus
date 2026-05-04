from datetime import datetime, timedelta, timezone

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
