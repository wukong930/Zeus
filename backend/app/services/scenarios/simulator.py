from __future__ import annotations

from app.services.risk.stress import symbol_prefix
from app.services.scenarios.monte_carlo import run_monte_carlo
from app.services.scenarios.types import ScenarioReport, ScenarioRequest, WhatIfResult
from app.services.scenarios.what_if import impact_for_symbol, run_what_if

DEFAULT_BASE_PRICES: dict[str, float] = {
    "RB": 3250.0,
    "HC": 3420.0,
    "I": 780.0,
    "J": 1980.0,
    "JM": 1520.0,
    "RU": 15400.0,
    "NR": 13260.0,
    "BR": 12100.0,
    "SC": 620.0,
    "FU": 3450.0,
    "TA": 5860.0,
    "EG": 4520.0,
    "CU": 76500.0,
    "AL": 20400.0,
    "ZN": 23500.0,
}

DEFAULT_DAILY_VOLATILITY: dict[str, float] = {
    "RB": 0.018,
    "HC": 0.018,
    "I": 0.026,
    "J": 0.024,
    "JM": 0.028,
    "RU": 0.021,
    "NR": 0.022,
    "BR": 0.024,
    "SC": 0.026,
    "FU": 0.025,
    "TA": 0.020,
    "EG": 0.021,
    "CU": 0.017,
    "AL": 0.016,
    "ZN": 0.018,
}


def run_scenario_simulation(request: ScenarioRequest) -> ScenarioReport:
    target_symbol = symbol_prefix(request.target_symbol)
    what_if = run_what_if(request.shocks, max_depth=request.max_depth)
    target_impact = impact_for_symbol(what_if, target_symbol)
    applied_shock = target_impact.total_shock if target_impact is not None else 0.0
    base_price = request.base_price or DEFAULT_BASE_PRICES.get(target_symbol, 100.0)
    volatility_pct = request.volatility_pct or DEFAULT_DAILY_VOLATILITY.get(target_symbol, 0.02)
    monte_carlo = run_monte_carlo(
        target_symbol=target_symbol,
        base_price=base_price,
        days=request.days,
        simulations=request.simulations,
        volatility_pct=volatility_pct,
        drift_pct=request.drift_pct,
        applied_shock=applied_shock,
        seed=request.seed,
    )
    return ScenarioReport(
        target_symbol=target_symbol,
        base_price=base_price,
        request=request,
        what_if=what_if,
        monte_carlo=monte_carlo,
        narrative=build_scenario_narrative(
            target_symbol=target_symbol,
            what_if=what_if,
            applied_shock=applied_shock,
            base_price=base_price,
            p50=monte_carlo.terminal_distribution["p50"],
            p5=monte_carlo.terminal_distribution["p5"],
            p95=monte_carlo.terminal_distribution["p95"],
            downside_probability=monte_carlo.downside_probability,
        ),
        risk_points=tuple(build_risk_points(target_symbol, what_if, applied_shock)),
        suggested_actions=tuple(build_suggested_actions(applied_shock, monte_carlo.downside_probability)),
    )


def build_scenario_narrative(
    *,
    target_symbol: str,
    what_if: WhatIfResult,
    applied_shock: float,
    base_price: float,
    p50: float,
    p5: float,
    p95: float,
    downside_probability: float,
) -> str:
    driver = _dominant_target_driver(target_symbol, what_if)
    direction = "上行" if applied_shock >= 0 else "下行"
    shock_pct = abs(applied_shock) * 100
    median_return = ((p50 - base_price) / base_price * 100) if base_price else 0.0
    return (
        f"{target_symbol} 场景推演显示，当前假设沿传导图形成约 {shock_pct:.1f}% 的"
        f"{direction}冲击，主导驱动为 {driver or '目标品种直接假设'}。"
        f"Monte Carlo 中位路径为 {p50:.0f}，相对基准 {median_return:+.1f}%；"
        f"P5/P95 区间为 {p5:.0f} 到 {p95:.0f}，跌破基准价概率约 "
        f"{downside_probability * 100:.1f}%。"
    )


def build_risk_points(
    target_symbol: str,
    what_if: WhatIfResult,
    applied_shock: float,
) -> list[str]:
    points: list[str] = []
    target_impact = impact_for_symbol(what_if, target_symbol)
    if target_impact is not None and target_impact.paths:
        path = target_impact.paths[0]
        points.append(
            f"{path.root_symbol}->{target_symbol} 是当前最强传导路径，贡献约 {path.impact * 100:+.1f}%。"
        )
    if abs(applied_shock) >= 0.08:
        points.append("目标冲击超过 8%，应按高波动场景处理保证金和止损。")
    elif abs(applied_shock) >= 0.04:
        points.append("目标冲击处于中等强度，适合联动成本模型和持仓敞口复核。")
    else:
        points.append("目标冲击偏温和，主要关注二阶传导是否被新事件放大。")
    if len(what_if.key_paths) >= 3:
        points.append("多个二阶路径同时有效，后续新闻或库存信号可能放大相关性。")
    return points


def build_suggested_actions(applied_shock: float, downside_probability: float) -> list[str]:
    if applied_shock > 0.06 and downside_probability < 0.4:
        return ["保留偏多观察，若成本端信号延续可小幅提高监控优先级。", "设置 P25 路径附近为回撤复核线。"]
    if applied_shock < -0.06:
        return ["降低多头暴露或等待反证信号。", "若已有空头，使用 P75 路径作为止盈复核线。"]
    if downside_probability > 0.55:
        return ["维持中性偏谨慎，优先检查持仓方向冲突。", "等待事件确认后再扩大仓位。"]
    return ["维持观察，使用 P5/P95 区间更新预警阈值。", "继续跟踪最强传导路径的源头品种。"]


def _dominant_target_driver(target_symbol: str, what_if: WhatIfResult) -> str | None:
    target_impact = impact_for_symbol(what_if, target_symbol)
    if target_impact is None:
        return None
    return target_impact.dominant_driver
