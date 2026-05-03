from dataclasses import dataclass
from typing import Iterable

from app.models.signal import SignalTrack

HIT_OUTCOMES = {"hit", "success", "win"}
MISS_OUTCOMES = {"miss", "failure", "loss"}


@dataclass(frozen=True)
class DecayDetection:
    decay_detected: bool
    cusum_score: float
    sample_size: int
    reason: str


def detect_decay(
    rows: Iterable[SignalTrack],
    *,
    baseline_hit_rate: float = 0.5,
    drift: float = 0.05,
    threshold: float = 3.0,
) -> DecayDetection:
    outcomes: list[int] = []
    for row in rows:
        outcome = row.outcome.lower()
        if outcome in HIT_OUTCOMES:
            outcomes.append(1)
        elif outcome in MISS_OUTCOMES:
            outcomes.append(0)

    cusum = 0.0
    max_cusum = 0.0
    for value in outcomes:
        cusum = max(0.0, cusum + (baseline_hit_rate - value - drift))
        max_cusum = max(max_cusum, cusum)

    decay_detected = max_cusum >= threshold
    return DecayDetection(
        decay_detected=decay_detected,
        cusum_score=max_cusum,
        sample_size=len(outcomes),
        reason=(
            f"Negative CUSUM {max_cusum:.2f} crossed threshold {threshold:.2f}."
            if decay_detected
            else f"Negative CUSUM {max_cusum:.2f} below threshold {threshold:.2f}."
        ),
    )
