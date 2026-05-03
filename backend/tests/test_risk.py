from datetime import datetime, timedelta, timezone

from app.services.risk.correlation import build_correlation_matrix
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


def test_calculate_var_returns_zero_for_empty_positions() -> None:
    result = calculate_var([], {})

    assert result.var95 == 0
    assert result.var99 == 0
    assert result.cvar95 == 0
    assert result.cvar99 == 0


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
