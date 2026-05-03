from dataclasses import dataclass
from typing import Iterable

from app.models.signal import SignalTrack

HIT_OUTCOMES = {"hit", "success", "win"}
MISS_OUTCOMES = {"miss", "failure", "loss"}


@dataclass(frozen=True)
class HitRateSummary:
    hits: int
    misses: int
    total: int
    hit_rate: float | None


def summarize_outcomes(rows: Iterable[SignalTrack]) -> HitRateSummary:
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
