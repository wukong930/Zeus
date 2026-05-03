from __future__ import annotations

from statistics import mean

from app.services.risk.types import CorrelationMatrix, RiskMarketPoint


def build_correlation_matrix(
    market_data_by_symbol: dict[str, list[RiskMarketPoint]],
    symbols: list[str],
    *,
    window: int = 60,
) -> CorrelationMatrix:
    returns_by_symbol = {
        symbol: _daily_returns(market_data_by_symbol.get(symbol, []), window=window)
        for symbol in symbols
    }

    matrix: list[list[float]] = [[0.0 for _ in symbols] for _ in symbols]
    for row_idx, left in enumerate(symbols):
        matrix[row_idx][row_idx] = 1.0
        for col_idx in range(row_idx + 1, len(symbols)):
            right = symbols[col_idx]
            corr = pearson_correlation(
                returns_by_symbol.get(left, []),
                returns_by_symbol.get(right, []),
            )
            matrix[row_idx][col_idx] = corr
            matrix[col_idx][row_idx] = corr

    return CorrelationMatrix(
        symbols=tuple(symbols),
        matrix=tuple(tuple(row) for row in matrix),
        window=window,
    )


def pearson_correlation(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 3:
        return 0.0

    x = left[-size:]
    y = right[-size:]
    x_mean = mean(x)
    y_mean = mean(y)
    numerator = sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in zip(x, y, strict=True))
    denominator_left = sum((x_value - x_mean) ** 2 for x_value in x) ** 0.5
    denominator_right = sum((y_value - y_mean) ** 2 for y_value in y) ** 0.5
    denominator = denominator_left * denominator_right
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def _daily_returns(data: list[RiskMarketPoint], *, window: int) -> list[float]:
    ordered = sorted(data, key=lambda point: point.timestamp)[-window - 1 :]
    returns: list[float] = []
    for idx in range(1, len(ordered)):
        previous = ordered[idx - 1].close
        current = ordered[idx].close
        if previous == 0:
            returns.append(0.0)
            continue
        daily_return = (current - previous) / previous
        returns.append(daily_return if _is_finite(daily_return) else 0.0)
    return returns


def _is_finite(value: float) -> bool:
    return value not in (float("inf"), float("-inf")) and value == value
