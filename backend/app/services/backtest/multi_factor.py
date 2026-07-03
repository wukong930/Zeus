"""Multi-factor composite over the validated cross-sectional factors.

The IC probe found several real factors in the same universe, all with a
NEGATIVE cross-sectional IC (high value -> low forward return): trailing
momentum (reversal), distance-from-MA (value), and volatility (low-vol). They
are the same 'reversion' flavour but combining them — z-score each factor
cross-sectionally per day, then weighted-sum — diversifies the noise and can lift
the information ratio. A high composite => short; low composite => long, exactly
like the single-factor reversal strategy (long the bottom-k by composite).
"""

from __future__ import annotations

import math


def cross_sectional_zscore(values: dict[str, float | None]) -> dict[str, float]:
    valid = {
        symbol: float(value)
        for symbol, value in values.items()
        if value is not None and math.isfinite(value)
    }
    if len(valid) < 2:
        return {}
    mean = sum(valid.values()) / len(valid)
    variance = sum((value - mean) ** 2 for value in valid.values()) / len(valid)
    std = math.sqrt(variance)
    if std <= 0:
        return {symbol: 0.0 for symbol in valid}
    return {symbol: (value - mean) / std for symbol, value in valid.items()}


def composite_score(
    factor_values: dict[str, dict[str, float | None]],
    *,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Weighted sum of per-factor cross-sectional z-scores (oriented high => short)."""

    zscores = {factor: cross_sectional_zscore(values) for factor, values in factor_values.items()}
    factor_weights = weights or {factor: 1.0 for factor in factor_values}

    symbols: set[str] = set()
    for z in zscores.values():
        symbols |= set(z)

    composite: dict[str, float] = {}
    for symbol in symbols:
        total = 0.0
        contributing = 0
        for factor, z in zscores.items():
            if symbol in z:
                total += factor_weights.get(factor, 1.0) * z[symbol]
                contributing += 1
        if contributing:
            composite[symbol] = total
    return composite
