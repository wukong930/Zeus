"""Single source of truth: signal_type -> outcome semantic class.

This mirrors which outcome helper each evaluator in ``evaluators/*.py`` actually
calls (see ``signals/outcomes.py``). It matters because a "hit" means a DIFFERENT
thing per class:

* ``directional`` — predicted the price DIRECTION (forward_return * direction > 0)
* ``mean_reversion`` — a spread SNAPPED BACK toward its mean
* ``volatility`` — volatility / range EXPANDED

Pooling hit rates from different classes into one "accuracy" number is a category
error: it conflates three distinct claims, and a change in the aggregate can be
driven purely by a shift in the MIX of signal types rather than by any change in
predictive quality. Consumers that report a cross-type hit rate must group by
``classify_semantics`` first (see ``calibration/hit_rate.summarize_outcomes_by_semantics``).
"""

from __future__ import annotations

from typing import Literal

OutcomeSemantics = Literal["directional", "mean_reversion", "volatility", "unknown"]

# Only these assert a price DIRECTION that can be scored as a cost-aware
# long/short return; the rest assert mean reversion or volatility expansion.
DIRECTIONAL_SIGNALS: frozenset[str] = frozenset(
    {
        "momentum",
        "basis_shift",
        "price_gap",
        "event_driven",
        "news_event",
        "rubber_supply_shock",
        "capacity_contraction",
        "marginal_capacity_squeeze",
        "median_pressure",
        "restart_expectation",
    }
)
MEAN_REVERSION_SIGNALS: frozenset[str] = frozenset({"spread_anomaly"})
VOLATILITY_SIGNALS: frozenset[str] = frozenset({"regime_shift", "inventory_shock"})


def classify_semantics(signal_type: str) -> OutcomeSemantics:
    if signal_type in DIRECTIONAL_SIGNALS:
        return "directional"
    if signal_type in MEAN_REVERSION_SIGNALS:
        return "mean_reversion"
    if signal_type in VOLATILITY_SIGNALS:
        return "volatility"
    return "unknown"
