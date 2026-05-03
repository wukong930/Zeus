from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdProfile:
    z_score_entry: float = 2.0
    z_score_exit: float = 0.5
    volume_spike: float = 30.0
    basis_deviation: float = 1.5
    hurst_shift: float = 0.15
    corr_break: float = 0.3
    min_confidence: float = 0.65
    half_life_cap: float = 30.0


_CATEGORY_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "ferrous": {"z_score_entry": 2.2, "basis_deviation": 1.7, "volume_spike": 25},
    "nonferrous": {"z_score_entry": 1.9, "basis_deviation": 1.4},
    "energy": {"z_score_entry": 2.3, "basis_deviation": 1.8, "corr_break": 0.35},
    "agriculture": {"z_score_entry": 2.0, "basis_deviation": 1.5, "half_life_cap": 25},
}

_REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "high": {
        "z_score_entry": 1.25,
        "z_score_exit": 0.8,
        "volume_spike": 0.75,
        "basis_deviation": 1.2,
        "corr_break": 1.15,
        "min_confidence": 1.1,
    },
    "low": {
        "z_score_entry": 0.9,
        "z_score_exit": 1.2,
        "volume_spike": 1.2,
        "basis_deviation": 0.9,
        "corr_break": 0.85,
        "min_confidence": 0.9,
    },
    "normal": {},
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def get_thresholds(
    category: str,
    *,
    volatility_regime: str = "normal",
    half_life: float | None = None,
) -> ThresholdProfile:
    values = ThresholdProfile().__dict__.copy()
    values.update(_CATEGORY_ADJUSTMENTS.get(category, {}))

    for key, multiplier in _REGIME_MULTIPLIERS.get(volatility_regime, {}).items():
        values[key] *= multiplier

    if half_life is not None and half_life > 0:
        if half_life <= 5:
            values["z_score_entry"] *= 0.9
            values["z_score_exit"] *= 1.3
        elif half_life > 20:
            values["z_score_entry"] *= 1.15
            values["z_score_exit"] *= 0.8

    values["z_score_entry"] = _clamp(values["z_score_entry"], 1.5, 3.5)
    values["z_score_exit"] = _clamp(values["z_score_exit"], 0.2, 1.0)
    values["volume_spike"] = _clamp(values["volume_spike"], 15, 60)
    values["basis_deviation"] = _clamp(values["basis_deviation"], 1.0, 2.5)
    values["hurst_shift"] = _clamp(values["hurst_shift"], 0.08, 0.25)
    values["corr_break"] = _clamp(values["corr_break"], 0.15, 0.5)
    values["min_confidence"] = _clamp(values["min_confidence"], 0.55, 0.8)
    return ThresholdProfile(**values)
