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
        "signal_types": sorted(_normalize_signal_types(signal_types)),
        "category": _normalize_label(category),
        "regime": _normalize_label(regime) or "unknown",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def jaccard_similarity(left: set[str] | frozenset[str], right: set[str] | frozenset[str]) -> float:
    left = _normalize_signal_types(left)
    right = _normalize_signal_types(right)
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
    force_mode: str | None = None,
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

    mode = force_mode or (MODE_ENFORCING if candidate.sample_size >= min_samples else MODE_INFORMATIONAL)
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
            "mode_source": "manual_warmup_override" if force_mode else "sample_size",
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
    normalized_category = _normalize_label(category)
    normalized_regime = _normalize_label(regime) or "unknown"
    normalized_signal_types = _normalize_signal_types(signal_types)
    for candidate in candidates:
        candidate_category = _normalize_label(candidate.category)
        candidate_regime = _normalize_label(candidate.regime) or "unknown"
        if candidate_category != normalized_category:
            continue
        if candidate_regime != normalized_regime and candidate_regime != "unknown":
            continue
        similarity = jaccard_similarity(normalized_signal_types, candidate.signal_types)
        if similarity >= min_similarity:
            matches.append((candidate, similarity))

    if not matches:
        return None, 0.0
    return sorted(matches, key=lambda item: (-item[1], -item[0].sample_size))[0]


def _normalize_signal_types(signal_types: set[str] | frozenset[str]) -> frozenset[str]:
    return frozenset(str(signal_type).strip().lower() for signal_type in signal_types if str(signal_type).strip())


def _normalize_label(value: str | None) -> str:
    return str(value or "").strip().lower()
