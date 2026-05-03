from __future__ import annotations

import math
from statistics import mean

from app.services.risk.types import RiskMarketPoint, RiskPosition, VaRResult


def calculate_var(
    positions: list[RiskPosition],
    market_data_by_symbol: dict[str, list[RiskMarketPoint]],
    *,
    horizon: int = 1,
) -> VaRResult:
    daily_pnls = _daily_position_pnls(positions, market_data_by_symbol)
    empty = VaRResult(var95=0, var99=0, cvar95=0, cvar99=0, horizon=horizon)
    if len(daily_pnls) < 10:
        return empty

    sorted_pnls = sorted(daily_pnls)
    size = len(sorted_pnls)
    idx95 = max(0, math.floor(size * 0.05))
    idx99 = max(0, math.floor(size * 0.01))

    hist_var95 = sorted_pnls[idx95]
    hist_var99 = sorted_pnls[idx99]
    hist_cvar95 = mean(sorted_pnls[: idx95 + 1])
    hist_cvar99 = mean(sorted_pnls[: max(idx99, 1)])

    sigma = _ewma_vol(daily_pnls, decay=0.94)
    avg = mean(daily_pnls)
    skew, excess_kurtosis = _shape(daily_pnls, avg)
    z95 = _cornish_fisher(1.645, skew, excess_kurtosis)
    z99 = _cornish_fisher(2.326, skew, excess_kurtosis)

    param_var95 = avg - sigma * z95
    param_var99 = avg - sigma * z99
    param_cvar95 = avg - sigma * _normal_pdf(z95) / 0.05
    param_cvar99 = avg - sigma * _normal_pdf(z99) / 0.01

    scale = math.sqrt(max(1, horizon))
    return VaRResult(
        var95=_round_currency(min(hist_var95, param_var95) * scale),
        var99=_round_currency(min(hist_var99, param_var99) * scale),
        cvar95=_round_currency(min(hist_cvar95, param_cvar95) * scale),
        cvar99=_round_currency(min(hist_cvar99, param_cvar99) * scale),
        horizon=horizon,
    )


def _daily_position_pnls(
    positions: list[RiskPosition],
    market_data_by_symbol: dict[str, list[RiskMarketPoint]],
) -> list[float]:
    pnls: list[float] = []
    for position in positions:
        if position.status != "open":
            continue
        for leg in position.legs:
            data = sorted(
                market_data_by_symbol.get(leg.asset, []),
                key=lambda point: point.timestamp,
            )[-504:]
            if len(data) < 2:
                continue
            direction = 1 if leg.direction == "long" else -1
            notional = leg.current_price * leg.size
            for idx in range(1, len(data)):
                previous = data[idx - 1].close
                current = data[idx].close
                if previous == 0:
                    continue
                daily_return = (current - previous) / previous
                pnls.append(daily_return * notional * direction)
    return pnls


def _ewma_vol(values: list[float], *, decay: float) -> float:
    if not values:
        return 0.0

    avg = mean(values)
    variance = 0.0
    weight = 1.0
    weight_sum = 0.0
    for value in reversed(values):
        variance += weight * (value - avg) ** 2
        weight_sum += weight
        weight *= decay
    return math.sqrt(variance / weight_sum) if weight_sum > 0 else 0.0


def _shape(values: list[float], avg: float) -> tuple[float, float]:
    size = len(values)
    m2 = sum((value - avg) ** 2 for value in values) / size
    if m2 <= 0:
        return 0.0, 0.0
    m3 = sum((value - avg) ** 3 for value in values) / size
    m4 = sum((value - avg) ** 4 for value in values) / size
    return m3 / (m2**1.5), m4 / (m2**2) - 3


def _cornish_fisher(z_score: float, skew: float, excess_kurtosis: float) -> float:
    skew = max(-2.0, min(2.0, skew))
    excess_kurtosis = max(-3.0, min(10.0, excess_kurtosis))
    return (
        z_score
        + (z_score**2 - 1) * skew / 6
        + (z_score**3 - 3 * z_score) * excess_kurtosis / 24
        - (2 * z_score**3 - 5 * z_score) * skew**2 / 36
    )


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2 * math.pi)


def _round_currency(value: float) -> float:
    rounded = round(value, 2)
    return 0.0 if rounded == -0.0 else rounded
