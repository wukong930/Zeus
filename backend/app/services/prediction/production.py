"""Bounded production influence for the governed forecast.

Even when a forecast is authoritative (decision_grade=True), production must
never consume its raw target weights directly — a model error could blow up the
book. ``bounded_weights`` caps each leg and the total gross exposure, so the
signal's influence is hard-limited. Production reads the bounded view, not the
raw signal.
"""

from __future__ import annotations

from app.models.forecast import ForecastRecord

DEFAULT_MAX_GROSS = 1.0
DEFAULT_MAX_PER_SYMBOL = 0.15


def bounded_weights(
    weights: dict[str, float],
    *,
    max_gross: float = DEFAULT_MAX_GROSS,
    max_per_symbol: float = DEFAULT_MAX_PER_SYMBOL,
) -> dict[str, float]:
    """Cap per-symbol weight then scale so total gross exposure <= max_gross."""

    capped = {
        symbol: max(-max_per_symbol, min(max_per_symbol, float(weight)))
        for symbol, weight in weights.items()
    }
    gross = sum(abs(weight) for weight in capped.values())
    if gross > max_gross and gross > 0:
        scale = max_gross / gross
        capped = {symbol: round(weight * scale, 6) for symbol, weight in capped.items()}
    return capped


def production_weights(
    forecast: ForecastRecord,
    *,
    max_gross: float = DEFAULT_MAX_GROSS,
    max_per_symbol: float = DEFAULT_MAX_PER_SYMBOL,
) -> dict[str, float]:
    """The weights production may actually use: bounded, and only if authoritative."""

    if not forecast.decision_grade:
        return {}  # advisory / shadow forecasts have zero production influence
    return bounded_weights(
        forecast.target_weights or {},
        max_gross=max_gross,
        max_per_symbol=max_per_symbol,
    )
