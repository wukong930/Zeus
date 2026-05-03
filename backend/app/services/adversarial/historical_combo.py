import hashlib
import json
from dataclasses import dataclass

from app.services.adversarial.types import (
    MODE_ENFORCING,
    MODE_INFORMATIONAL,
    AdversarialCheckResult,
)

MIN_ENFORCING_SAMPLES = 20
MIN_ACCEPTABLE_HIT_RATE = 0.3
MIN_JACCARD_SIMILARITY = 0.7


@dataclass(frozen=True)
class HistoricalComboCandidate:
    signal_types: frozenset[str]
    category: str
    regime: str
    hit_rate: float | None
    sample_size: int


def fuzzy_combo_hash(
    *,
    signal_types: set[str] | frozenset[str],
    category: str,
    regime: str,
) -> str:
    payload = {
        "signal_types": sorted(signal_types),
        "category": category,
        "regime": regime or "unknown",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def jaccard_similarity(left: set[str] | frozenset[str], right: set[str] | frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    union = set(left) | set(right)
    if not union:
        return 0.0
    return len(set(left) & set(right)) / len(union)


def evaluate_historical_combo(
    *,
    signal_types: set[str] | frozenset[str],
    category: str,
    regime: str,
    candidates: list[HistoricalComboCandidate],
    min_samples: int = MIN_ENFORCING_SAMPLES,
    min_hit_rate: float = MIN_ACCEPTABLE_HIT_RATE,
    min_similarity: float = MIN_JACCARD_SIMILARITY,
) -> AdversarialCheckResult:
    candidate, similarity = best_historical_candidate(
        signal_types=signal_types,
        category=category,
        regime=regime,
        candidates=candidates,
        min_similarity=min_similarity,
    )
    if candidate is None:
        return AdversarialCheckResult(
            check_name="historical_combo",
            passed=True,
            mode=MODE_INFORMATIONAL,
            sample_size=0,
            reason="No similar historical combo exists yet.",
            details={
                "combo_hash": fuzzy_combo_hash(
                    signal_types=signal_types,
                    category=category,
                    regime=regime,
                ),
                "similarity": 0,
            },
        )

    mode = MODE_ENFORCING if candidate.sample_size >= min_samples else MODE_INFORMATIONAL
    hit_rate = candidate.hit_rate if candidate.hit_rate is not None else 0.5
    passed = hit_rate >= min_hit_rate
    return AdversarialCheckResult(
        check_name="historical_combo",
        passed=passed,
        mode=mode,
        score=hit_rate,
        sample_size=candidate.sample_size,
        reason=(
            f"Best historical combo hit-rate {hit_rate:.4f} from "
            f"{candidate.sample_size} samples."
        ),
        details={
            "combo_hash": fuzzy_combo_hash(
                signal_types=signal_types,
                category=category,
                regime=regime,
            ),
            "matched_signal_types": sorted(candidate.signal_types),
            "similarity": similarity,
            "min_hit_rate": min_hit_rate,
            "min_enforcing_samples": min_samples,
        },
    )


def best_historical_candidate(
    *,
    signal_types: set[str] | frozenset[str],
    category: str,
    regime: str,
    candidates: list[HistoricalComboCandidate],
    min_similarity: float = MIN_JACCARD_SIMILARITY,
) -> tuple[HistoricalComboCandidate | None, float]:
    matches: list[tuple[HistoricalComboCandidate, float]] = []
    for candidate in candidates:
        if candidate.category != category:
            continue
        if candidate.regime != regime and candidate.regime != "unknown":
            continue
        similarity = jaccard_similarity(signal_types, candidate.signal_types)
        if similarity >= min_similarity:
            matches.append((candidate, similarity))

    if not matches:
        return None, 0.0
    return sorted(matches, key=lambda item: (-item[1], -item[0].sample_size))[0]
