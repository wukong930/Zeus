import math

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
