from __future__ import annotations

import re
from statistics import mean

from app.services.risk.types import (
    PositionImpact,
    RiskMarketPoint,
    RiskPosition,
    StressScenario,
    StressTestResult,
)


STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario(
        name="商品暴跌",
        description="所有商品价格下跌 20%",
        shocks={"RB": -0.20, "HC": -0.20, "I": -0.20, "CU": -0.20, "AL": -0.20, "SC": -0.20, "NI": -0.20, "ZN": -0.20},
    ),
    StressScenario(
        name="黑色系崩盘",
        description="黑色系品种下跌 25%，有色下跌 10%",
        shocks={"RB": -0.25, "HC": -0.25, "I": -0.25, "J": -0.25, "JM": -0.25, "CU": -0.10, "AL": -0.10, "NI": -0.10},
    ),
    StressScenario(
        name="美元飙升",
        description="美元走强导致有色金属下跌 15%，黑色系下跌 5%",
        shocks={"CU": -0.15, "AL": -0.15, "NI": -0.15, "ZN": -0.15, "AU": -0.10, "AG": -0.12, "RB": -0.05, "HC": -0.05},
    ),
    StressScenario(
        name="流动性冻结",
        description="所有品种下跌 10%，模拟流动性危机",
        shocks={"RB": -0.10, "HC": -0.10, "I": -0.10, "CU": -0.10, "AL": -0.10, "SC": -0.10, "NI": -0.10, "ZN": -0.10},
    ),
    StressScenario(
        name="通胀飙升",
        description="能源和农产品上涨 15%，金属下跌 5%",
        shocks={"SC": 0.15, "FU": 0.15, "CU": -0.05, "AL": -0.05, "RB": 0.05, "HC": 0.05},
    ),
    StressScenario(
        name="2022 黑色系限产",
        description="限产政策导致螺纹钢暴涨，铁矿石暴跌",
        shocks={"RB": 0.15, "HC": 0.12, "I": -0.25, "J": -0.20, "JM": -0.18, "CU": -0.03, "AL": -0.02},
        historical=True,
    ),
    StressScenario(
        name="2020 原油负价格",
        description="原油暴跌，能化链全面崩溃",
        shocks={"SC": -0.40, "FU": -0.35, "TA": -0.20, "EG": -0.18, "RB": -0.05, "CU": -0.08},
        historical=True,
    ),
    StressScenario(
        name="2023 硅铁锰硅暴涨",
        description="合金品种供给收缩导致暴涨",
        shocks={"SF": 0.30, "SM": 0.25, "RB": 0.05, "HC": 0.05, "I": 0.03},
        historical=True,
    ),
)


def run_stress_test(
    positions: list[RiskPosition],
    scenarios: tuple[StressScenario, ...] | list[StressScenario] | None = None,
) -> list[StressTestResult]:
    results: list[StressTestResult] = []
    for scenario in scenarios or STRESS_SCENARIOS:
        portfolio_pnl = 0.0
        impacts: list[PositionImpact] = []

        for position in positions:
            if position.status != "open":
                continue

            position_pnl = 0.0
            for leg in position.legs:
                shock = scenario.shocks.get(symbol_prefix(leg.asset), 0.0)
                direction = 1 if leg.direction == "long" else -1
                position_pnl += leg.current_price * leg.size * shock * direction

            portfolio_pnl += position_pnl
            impacts.append(
                PositionImpact(
                    position_id=position.id,
                    strategy_name=position.strategy_name or position.id,
                    pnl=_round_currency(position_pnl),
                )
            )

        results.append(
            StressTestResult(
                scenario=scenario.name,
                description=scenario.description,
                portfolio_pnl=_round_currency(portfolio_pnl),
                position_impacts=tuple(impacts),
            )
        )

    return results


def extract_historical_extremes(
    market_data_by_symbol: dict[str, list[RiskMarketPoint]],
    *,
    max_scenarios: int = 5,
) -> list[StressScenario]:
    returns_by_symbol = _returns_by_symbol(market_data_by_symbol)
    extreme_days: list[tuple[str, str, float, float]] = []

    for symbol, returns in returns_by_symbol.items():
        if len(returns) < 20:
            continue
        values = [ret for _, ret in returns]
        avg = mean(values)
        std_dev = _std_dev(values, avg)
        if std_dev == 0:
            continue
        for date, ret in returns:
            sigma = abs((ret - avg) / std_dev)
            if sigma > 3:
                extreme_days.append((date, symbol, ret, sigma))

    extreme_days.sort(key=lambda item: item[3], reverse=True)
    seen_dates: set[str] = set()
    scenarios: list[StressScenario] = []

    for date, symbol, _, sigma in extreme_days:
        if date in seen_dates or len(scenarios) >= max_scenarios:
            continue
        seen_dates.add(date)

        day_returns: list[float] = []
        normal_returns: list[float] = []
        for returns in returns_by_symbol.values():
            day_return = next((ret for return_date, ret in returns if return_date == date), None)
            if day_return is not None:
                day_returns.append(abs(day_return))
            normal_returns.append(mean(abs(ret) for _, ret in returns))

        avg_extreme = mean(day_returns) if day_returns else 0.0
        avg_normal = mean(normal_returns) if normal_returns else 0.0
        tail_boost = (
            min(2.0, max(1.0, avg_extreme / avg_normal))
            if avg_normal > 0 and len(day_returns) >= 5
            else 1.3
        )

        shocks: dict[str, float] = {}
        for shock_symbol, returns in returns_by_symbol.items():
            day_return = next((ret for return_date, ret in returns if return_date == date), None)
            if day_return is None:
                continue
            adjusted = day_return * (tail_boost if abs(day_return) > 0.03 else 1.0)
            shocks[symbol_prefix(shock_symbol)] = round(adjusted, 3)

        scenarios.append(
            StressScenario(
                name=f"历史极端日 {date[:10]}",
                description=f"{symbol} 偏离 {sigma:.1f}σ，尾部相关性调整",
                shocks=shocks,
                historical=True,
            )
        )

    return scenarios


def _returns_by_symbol(
    market_data_by_symbol: dict[str, list[RiskMarketPoint]],
) -> dict[str, list[tuple[str, float]]]:
    returns_by_symbol: dict[str, list[tuple[str, float]]] = {}
    for symbol, data in market_data_by_symbol.items():
        if len(data) < 2:
            continue
        ordered = sorted(data, key=lambda point: point.timestamp)
        returns: list[tuple[str, float]] = []
        for idx in range(1, len(ordered)):
            previous = ordered[idx - 1].close
            current = ordered[idx].close
            if previous == 0:
                continue
            returns.append((ordered[idx].timestamp.isoformat(), (current - previous) / previous))
        returns_by_symbol[symbol] = returns
    return returns_by_symbol


def symbol_prefix(symbol: str) -> str:
    return re.sub(r"\d+", "", symbol).upper()


def _std_dev(values: list[float], avg: float) -> float:
    return (sum((value - avg) ** 2 for value in values) / len(values)) ** 0.5


def _round_currency(value: float) -> float:
    rounded = round(value, 2)
    return 0.0 if rounded == -0.0 else rounded
