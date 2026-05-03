from statistics import mean
from typing import Any

from app.services.signals.helpers import log_returns, std_dev
from app.services.signals.types import MarketBar, OutcomeEvaluation

HORIZONS = (1, 5, 20)


def sorted_bars(market_data: list[MarketBar], horizon_days: int | None = None) -> list[MarketBar]:
    ordered = sorted(market_data, key=lambda bar: bar.timestamp)
    if horizon_days is None:
        return ordered
    return ordered[: max(1, horizon_days + 1)]


def forward_return_map(market_data: list[MarketBar]) -> dict[int, float | None]:
    ordered = sorted_bars(market_data)
    returns: dict[int, float | None] = {horizon: None for horizon in HORIZONS}
    if len(ordered) < 2 or ordered[0].close == 0:
        return returns

    base = ordered[0].close
    for horizon in HORIZONS:
        if len(ordered) > horizon:
            returns[horizon] = (ordered[horizon].close - base) / base
    return returns


def outcome_result(
    *,
    outcome: str,
    reason: str,
    horizon_days: int,
    market_data: list[MarketBar],
) -> OutcomeEvaluation:
    returns = forward_return_map(market_data)
    return OutcomeEvaluation(
        outcome=outcome,
        reason=reason,
        horizon_days=horizon_days,
        forward_return_1d=returns[1],
        forward_return_5d=returns[5],
        forward_return_20d=returns[20],
    )


def pending_result(reason: str, horizon_days: int, market_data: list[MarketBar]) -> OutcomeEvaluation:
    return outcome_result(
        outcome="pending",
        reason=reason,
        horizon_days=horizon_days,
        market_data=market_data,
    )


def direction_from_signal(signal: dict[str, Any]) -> int:
    text = " ".join(
        str(item).lower()
        for item in (
            signal.get("title", ""),
            signal.get("summary", ""),
            *signal.get("risk_items", []),
        )
    )
    if any(marker in text for marker in ("bullish", " up", "up.", "上行", "long")):
        return 1
    if any(marker in text for marker in ("bearish", " down", "down.", "下行", "short")):
        return -1
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("z_score") is not None:
        return 1 if float(spread_info["z_score"]) > 0 else -1
    return 0


def directional_outcome(
    *,
    signal: dict[str, Any],
    market_data: list[MarketBar],
    horizon_days: int,
    min_abs_return: float = 0.0,
) -> OutcomeEvaluation:
    ordered = sorted_bars(market_data, horizon_days)
    if len(ordered) < 2 or ordered[0].close == 0:
        return pending_result("Not enough forward market data.", horizon_days, ordered)

    direction = direction_from_signal(signal)
    if direction == 0:
        return pending_result("Signal direction is unknown.", horizon_days, ordered)

    forward_return = (ordered[-1].close - ordered[0].close) / ordered[0].close
    hit = forward_return * direction > min_abs_return
    return outcome_result(
        outcome="hit" if hit else "miss",
        reason=f"Forward return {forward_return:.4f} versus direction {direction}.",
        horizon_days=horizon_days,
        market_data=ordered,
    )


def volatility_expansion_outcome(
    *,
    market_data: list[MarketBar],
    horizon_days: int,
    min_ratio: float = 1.2,
) -> OutcomeEvaluation:
    ordered = sorted_bars(market_data, horizon_days)
    if len(ordered) < 8:
        return pending_result("Not enough forward market data.", horizon_days, ordered)

    closes = [bar.close for bar in ordered]
    returns = log_returns(closes)
    if len(returns) < 6:
        return pending_result("Not enough forward returns.", horizon_days, ordered)

    midpoint = max(2, len(returns) // 2)
    early = returns[:midpoint]
    late = returns[midpoint:]
    early_vol = std_dev(early)
    late_vol = std_dev(late)
    ratio = late_vol / early_vol if early_vol > 0 else 1.0
    return outcome_result(
        outcome="hit" if ratio >= min_ratio else "miss",
        reason=f"Forward volatility ratio {ratio:.2f}.",
        horizon_days=horizon_days,
        market_data=ordered,
    )


def range_expansion_outcome(
    *,
    market_data: list[MarketBar],
    horizon_days: int,
    min_range_ratio: float = 0.03,
) -> OutcomeEvaluation:
    ordered = sorted_bars(market_data, horizon_days)
    if not ordered:
        return pending_result("Not enough forward market data.", horizon_days, ordered)

    ranges = [(bar.high - bar.low) / bar.close for bar in ordered if bar.close > 0]
    if not ranges:
        return pending_result("No valid forward ranges.", horizon_days, ordered)
    average_range = mean(ranges)
    return outcome_result(
        outcome="hit" if average_range >= min_range_ratio else "miss",
        reason=f"Average forward range ratio {average_range:.4f}.",
        horizon_days=horizon_days,
        market_data=ordered,
    )
