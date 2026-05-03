import math
from statistics import mean

from app.services.signals.types import TriggerStep


def build_trigger_step(step: int, label: str, description: str, confidence: float) -> TriggerStep:
    return TriggerStep(step=step, label=label, description=description, confidence=confidence)


def severity_from_z_score(z_score: float) -> str:
    abs_z = abs(z_score)
    if abs_z > 3.0:
        return "critical"
    if abs_z > 2.5:
        return "high"
    if abs_z > 2.0:
        return "medium"
    return "low"


def moving_average(data: list[float], window: int) -> list[float]:
    result: list[float] = []
    for idx in range(len(data)):
        if idx < window - 1:
            result.append(math.nan)
            continue

        window_values = data[idx - window + 1 : idx + 1]
        result.append(sum(window_values) / window)
    return result


def volume_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0
    return ((current - previous) / previous) * 100


def std_dev(values: list[float]) -> float:
    if not values:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def log_returns(closes: list[float]) -> list[float]:
    returns: list[float] = []
    for idx in range(1, len(closes)):
        previous = closes[idx - 1]
        current = closes[idx]
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous))
    return returns


def hurst_exponent(values: list[float]) -> float:
    if len(values) < 8:
        return 0.5

    avg = mean(values)
    deviations = [value - avg for value in values]
    cumulative: list[float] = []
    running = 0.0
    for value in deviations:
        running += value
        cumulative.append(running)

    value_range = max(cumulative) - min(cumulative)
    sd = std_dev(values)
    if sd == 0:
        return 0.5

    rescaled_range = value_range / sd
    if rescaled_range <= 0:
        return 0.5

    estimate = math.log(rescaled_range) / math.log(len(values))
    return max(0.0, min(1.0, estimate))


def pearson_correlation(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0

    x = left[-size:]
    y = right[-size:]
    x_mean = mean(x)
    y_mean = mean(y)
    numerator = sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y, strict=True))
    x_denominator = math.sqrt(sum((xv - x_mean) ** 2 for xv in x))
    y_denominator = math.sqrt(sum((yv - y_mean) ** 2 for yv in y))
    denominator = x_denominator * y_denominator
    if denominator == 0:
        return 0.0
    return numerator / denominator
