from datetime import date

from app.services.adversarial.engine import decide_adversarial_outcome
from app.services.adversarial.historical_combo import (
    HistoricalComboCandidate,
    evaluate_historical_combo,
    fuzzy_combo_hash,
    jaccard_similarity,
)
from app.services.adversarial.null_hypothesis import (
    NullDistributionSummary,
    evaluate_null_hypothesis,
)
from app.services.adversarial.structural_counter import (
    StructuralEdge,
    evaluate_structural_counter,
)
from app.services.adversarial.types import (
    MODE_ENFORCING,
    MODE_INFORMATIONAL,
    AdversarialCheckResult,
)


def test_null_hypothesis_rejects_noise_like_signal() -> None:
    cache = NullDistributionSummary(
        signal_type="spread_anomaly",
        category="ferrous",
        computed_for=date(2026, 5, 3),
        sample_size=5,
        distribution_stats={"samples": [1, 1.2, 1.4, 1.6, 1.8], "sample_size": 5},
    )

    result = evaluate_null_hypothesis(
        {"signal_type": "spread_anomaly", "spread_info": {"z_score": 1.1}},
        cache,
    )

    assert result.passed is False
    assert result.score is not None
    assert result.score > 0.05


def test_null_hypothesis_passes_large_cached_deviation() -> None:
    cache = NullDistributionSummary(
        signal_type="spread_anomaly",
        category="ferrous",
        computed_for=date(2026, 5, 3),
        sample_size=5,
        distribution_stats={"samples": [1, 1.2, 1.4, 1.6, 1.8], "sample_size": 5},
    )

    result = evaluate_null_hypothesis(
        {"signal_type": "spread_anomaly", "spread_info": {"z_score": 3.0}},
        cache,
    )

    assert result.passed is True
    assert result.score == 0.01


def test_historical_combo_fuzzy_match_fails_in_enforcing_mode() -> None:
    result = evaluate_historical_combo(
        signal_types={"spread_anomaly", "basis_shift", "momentum"},
        category="ferrous",
        regime="range_low_vol",
        candidates=[
            HistoricalComboCandidate(
                signal_types=frozenset(
                    {"spread_anomaly", "basis_shift", "momentum", "regime_shift"}
                ),
                category="ferrous",
                regime="range_low_vol",
                hit_rate=0.2,
                sample_size=30,
            )
        ],
    )

    assert result.passed is False
    assert result.mode == MODE_ENFORCING
    assert result.score == 0.2
    assert jaccard_similarity({"a", "b"}, {"a", "b", "c"}) >= 0.66
    assert fuzzy_combo_hash(
        signal_types={"basis_shift", "spread_anomaly"},
        category="ferrous",
        regime="range_low_vol",
    ) == fuzzy_combo_hash(
        signal_types={"spread_anomaly", "basis_shift"},
        category="ferrous",
        regime="range_low_vol",
    )


def test_historical_combo_low_sample_failure_is_informational() -> None:
    result = evaluate_historical_combo(
        signal_types={"spread_anomaly"},
        category="ferrous",
        regime="range_low_vol",
        candidates=[
            HistoricalComboCandidate(
                signal_types=frozenset({"spread_anomaly"}),
                category="ferrous",
                regime="range_low_vol",
                hit_rate=0.1,
                sample_size=5,
            )
        ],
    )

    assert result.passed is False
    assert result.mode == MODE_INFORMATIONAL


def test_historical_combo_warmup_override_forces_informational_mode() -> None:
    result = evaluate_historical_combo(
        signal_types={"spread_anomaly", "basis_shift"},
        category="ferrous",
        regime="range_low_vol",
        candidates=[
            HistoricalComboCandidate(
                signal_types=frozenset({"spread_anomaly", "basis_shift"}),
                category="ferrous",
                regime="range_low_vol",
                hit_rate=0.1,
                sample_size=120,
            )
        ],
        force_mode=MODE_INFORMATIONAL,
    )

    assert result.passed is False
    assert result.mode == MODE_INFORMATIONAL
    assert result.details is not None
    assert result.details["mode_source"] == "manual_warmup_override"


def test_structural_counter_fails_on_reverse_path_and_context_pressure() -> None:
    result = evaluate_structural_counter(
        signal={"signal_type": "momentum", "related_assets": ["RB"]},
        context={"seasonal_factor": -0.4, "substitute_pressure": 0.8},
        edges=[
            StructuralEdge(
                source_symbol="RB",
                target_symbol="HC",
                type="substitute",
                strength=0.7,
                propagation_direction=-1,
            )
        ],
    )

    assert result.passed is False
    assert result.sample_size == 3


def test_warmup_historical_failure_does_not_suppress_signal() -> None:
    decision = decide_adversarial_outcome(
        signal={"signal_type": "spread_anomaly", "confidence": 0.8},
        signal_combination_hash="hash",
        results=[
            AdversarialCheckResult("null_hypothesis", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("historical_combo", passed=False, mode=MODE_INFORMATIONAL),
            AdversarialCheckResult("structural_counter", passed=False, mode=MODE_ENFORCING),
        ],
    )

    assert decision.suppressed is False
    assert decision.confidence_multiplier == 0.7
    assert round(decision.adjusted_signal["confidence"], 2) == 0.56
    assert decision.to_payload()["runtime_mode"] == "warmup"
    assert decision.to_payload()["warmup_enabled"] is True


def test_all_enforcing_failures_suppress_signal() -> None:
    decision = decide_adversarial_outcome(
        signal={"signal_type": "spread_anomaly", "confidence": 0.8},
        signal_combination_hash="hash",
        results=[
            AdversarialCheckResult("null_hypothesis", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("historical_combo", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("structural_counter", passed=False, mode=MODE_ENFORCING),
        ],
    )

    assert decision.suppressed is True
    assert decision.confidence_multiplier == 0.0
