"""Hit-rate summaries over resolved ``SignalTrack`` rows.

A "hit" means a different thing per signal semantic class (direction predicted /
spread reverted / volatility expanded), so a single pooled hit rate across classes
is a category error — use ``summarize_outcomes_by_semantics`` whenever the rows can
span more than one signal type. ``summarize_outcomes`` stays for the per-class /
single-signal-type case and for callers that explicitly want the raw pooled count.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from app.models.signal import SignalTrack
from app.services.signals.semantics import OutcomeSemantics, classify_semantics

HIT_OUTCOMES = {"hit", "success", "win"}
MISS_OUTCOMES = {"miss", "failure", "loss"}


@dataclass(frozen=True)
class HitRateSummary:
    hits: int
    misses: int
    total: int
    hit_rate: float | None


def summarize_outcomes(rows: Iterable[SignalTrack]) -> HitRateSummary:
    """Pooled hit/miss count over ``rows``.

    Semantic-agnostic: only meaningful within ONE semantic class (e.g. a single
    signal_type). Pooling directional + mean-reversion + volatility outcomes here
    conflates three distinct claims — prefer ``summarize_outcomes_by_semantics``.
    """

    hits = 0
    misses = 0
    for row in rows:
        outcome = row.outcome.lower()
        if outcome in HIT_OUTCOMES:
            hits += 1
        elif outcome in MISS_OUTCOMES:
            misses += 1

    total = hits + misses
    return HitRateSummary(
        hits=hits,
        misses=misses,
        total=total,
        hit_rate=hits / total if total else None,
    )


def summarize_outcomes_by_semantics(
    rows: Iterable[SignalTrack],
) -> dict[OutcomeSemantics, HitRateSummary]:
    """Hit rate split by outcome semantic class — the honest cross-type view.

    Groups rows by ``classify_semantics(row.signal_type)`` and summarizes each
    group independently, so a directional accuracy is never blended with a
    volatility-expansion or mean-reversion hit rate. Only classes actually present
    in ``rows`` appear in the result.
    """

    grouped: dict[OutcomeSemantics, list[SignalTrack]] = defaultdict(list)
    for row in rows:
        grouped[classify_semantics(row.signal_type)].append(row)
    return {semantics: summarize_outcomes(group) for semantics, group in grouped.items()}
