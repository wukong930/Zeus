from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PathMetrics:
    total_return: float
    max_drawdown: float
    underwater_durations: tuple[int, ...]
    pain_ratio: float
    recovery_factor: float
    cvar95: float
    mae_p50: float | None = None
    mae_p80: float | None = None
    mfe_p50: float | None = None
    mfe_p80: float | None = None

    def to_dict(self) -> dict:
        return {
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "underwater_durations": list(self.underwater_durations),
            "pain_ratio": round(self.pain_ratio, 6),
            "recovery_factor": round(self.recovery_factor, 6),
            "cvar95": round(self.cvar95, 6),
            "mae_p50": None if self.mae_p50 is None else round(self.mae_p50, 6),
            "mae_p80": None if self.mae_p80 is None else round(self.mae_p80, 6),
            "mfe_p50": None if self.mfe_p50 is None else round(self.mfe_p50, 6),
            "mfe_p80": None if self.mfe_p80 is None else round(self.mfe_p80, 6),
        }


def calculate_path_metrics(
    returns: list[float],
    *,
    mae_values: list[float] | None = None,
    mfe_values: list[float] | None = None,
) -> PathMetrics:
    equity = equity_curve(returns)
    drawdowns = drawdown_series(equity)
    max_drawdown = min(drawdowns) if drawdowns else 0.0
    underwater = underwater_durations(drawdowns)
    total_return = equity[-1] - 1 if equity else 0.0
    average_drawdown = abs(sum(drawdowns) / len(drawdowns)) if drawdowns else 0.0
    avg_return = sum(returns) / len(returns) if returns else 0.0
    return PathMetrics(
        total_return=total_return,
        max_drawdown=max_drawdown,
        underwater_durations=tuple(underwater),
        pain_ratio=avg_return / average_drawdown if average_drawdown > 0 else 0.0,
        recovery_factor=total_return / abs(max_drawdown) if max_drawdown < 0 else 0.0,
        cvar95=conditional_value_at_risk(returns, confidence=0.95),
        mae_p50=_percentile(mae_values or [], 0.50),
        mae_p80=_percentile(mae_values or [], 0.80),
        mfe_p50=_percentile(mfe_values or [], 0.50),
        mfe_p80=_percentile(mfe_values or [], 0.80),
    )


def equity_curve(returns: list[float], *, start: float = 1.0) -> list[float]:
    equity: list[float] = []
    value = start
    for item in returns:
        value *= 1 + item
        equity.append(value)
    return equity


def drawdown_series(equity: list[float]) -> list[float]:
    peak = 0.0
    drawdowns: list[float] = []
    for value in equity:
        peak = max(peak, value)
        drawdowns.append((value - peak) / peak if peak > 0 else 0.0)
    return drawdowns


def underwater_durations(drawdowns: list[float]) -> list[int]:
    durations: list[int] = []
    current = 0
    for drawdown in drawdowns:
        if drawdown < 0:
            current += 1
            continue
        if current:
            durations.append(current)
            current = 0
    if current:
        durations.append(current)
    return durations


def conditional_value_at_risk(returns: list[float], *, confidence: float = 0.95) -> float:
    if not returns:
        return 0.0
    ordered = sorted(returns)
    tail_count = max(1, round(len(ordered) * (1 - confidence)))
    return sum(ordered[:tail_count]) / tail_count


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
