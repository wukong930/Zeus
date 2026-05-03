from __future__ import annotations

import random

from app.services.scenarios.types import MonteCarloResult

MIN_PRICE = 0.01


def run_monte_carlo(
    *,
    target_symbol: str,
    base_price: float,
    days: int,
    simulations: int,
    volatility_pct: float,
    drift_pct: float = 0.0,
    applied_shock: float = 0.0,
    seed: int = 7,
    sample_path_count: int = 8,
) -> MonteCarloResult:
    rng = random.Random(seed)
    terminal_prices: list[float] = []
    sample_paths: list[tuple[float, ...]] = []
    effective_days = max(1, days)
    effective_simulations = max(1, simulations)
    daily_drift = drift_pct / effective_days

    for simulation_index in range(effective_simulations):
        price = max(MIN_PRICE, base_price * (1 + applied_shock))
        path = [round(base_price, 4), round(price, 4)]
        for _ in range(1, effective_days):
            daily_return = daily_drift + rng.gauss(0.0, volatility_pct)
            price = max(MIN_PRICE, price * (1 + max(-0.95, daily_return)))
            path.append(round(price, 4))
        terminal_prices.append(price)
        if simulation_index < sample_path_count:
            sample_paths.append(tuple(path))

    ordered = sorted(terminal_prices)
    expected_terminal_price = sum(terminal_prices) / len(terminal_prices)
    return MonteCarloResult(
        target_symbol=target_symbol,
        base_price=base_price,
        days=days,
        simulations=simulations,
        volatility_pct=volatility_pct,
        drift_pct=drift_pct,
        applied_shock=applied_shock,
        terminal_distribution={
            "p5": _percentile(ordered, 0.05),
            "p25": _percentile(ordered, 0.25),
            "p50": _percentile(ordered, 0.50),
            "p75": _percentile(ordered, 0.75),
            "p95": _percentile(ordered, 0.95),
        },
        expected_terminal_price=expected_terminal_price,
        expected_return=(expected_terminal_price - base_price) / base_price if base_price else 0.0,
        downside_probability=sum(1 for price in terminal_prices if price < base_price)
        / len(terminal_prices),
        sample_paths=tuple(sample_paths),
        seed=seed,
    )


def _percentile(ordered_values: list[float], percentile: float) -> float:
    if not ordered_values:
        return 0.0
    if len(ordered_values) == 1:
        return ordered_values[0]
    position = (len(ordered_values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered_values) - 1)
    weight = position - lower_index
    return ordered_values[lower_index] * (1 - weight) + ordered_values[upper_index] * weight
