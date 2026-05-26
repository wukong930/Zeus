from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.services.adversarial.engine import decide_adversarial_outcome
from app.services.adversarial.historical_combo import (
    HistoricalComboCandidate,
    evaluate_historical_combo,
    fuzzy_combo_hash,
    jaccard_similarity,
)
from app.services.adversarial.null_hypothesis import (
    NullDistributionSummary,
    _latest_null_distribution_cache_statement,
    _null_distribution_source_signals_statement,
    evaluate_null_hypothesis,
)
from app.services.adversarial.structural_counter import (
    StructuralEdge,
    evaluate_structural_counter,
    normalize_symbols,
    structural_edges_statement,
    structural_nodes_statement,
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


def test_null_distribution_cache_statement_uses_stable_latest_ordering() -> None:
    compiled = _compile_postgres(
        _latest_null_distribution_cache_statement(
            signal_type="spread_anomaly",
            category="ferrous",
            as_of_date=date(2026, 5, 3),
        )
    )

    assert "null_distribution_cache.signal_type = 'spread_anomaly'" in compiled
    assert "null_distribution_cache.category = 'ferrous'" in compiled
    assert "null_distribution_cache.computed_for <= '2026-05-03'" in compiled
    assert (
        "ORDER BY null_distribution_cache.computed_for DESC, "
        "null_distribution_cache.id DESC"
    ) in compiled
    assert "LIMIT 1" in compiled


def test_null_distribution_source_statement_is_point_in_time_and_stable() -> None:
    compiled = _compile_postgres(
        _null_distribution_source_signals_statement(
            since=datetime(2026, 5, 1, tzinfo=timezone.utc),
            as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
        )
    )

    assert "signal_track.created_at >= '2026-05-01 00:00:00+00:00'" in compiled
    assert "signal_track.created_at <= '2026-05-03 00:00:00+00:00'" in compiled
    assert "ORDER BY signal_track.created_at ASC, signal_track.id ASC" in compiled


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


def test_historical_combo_normalizes_scope_and_signal_types() -> None:
    result = evaluate_historical_combo(
        signal_types={" Spread_Anomaly ", "basis_shift"},
        category=" Ferrous ",
        regime=" Range_Low_Vol ",
        candidates=[
            HistoricalComboCandidate(
                signal_types=frozenset({"spread_anomaly", " Basis_Shift "}),
                category="ferrous",
                regime="range_low_vol",
                hit_rate=0.8,
                sample_size=30,
            )
        ],
    )

    assert result.passed is True
    assert result.score == 0.8
    assert jaccard_similarity({" Spread_Anomaly "}, {"spread_anomaly"}) == 1.0
    assert fuzzy_combo_hash(
        signal_types={" Spread_Anomaly ", "basis_shift"},
        category=" Ferrous ",
        regime=" Range_Low_Vol ",
    ) == fuzzy_combo_hash(
        signal_types={"basis_shift", "spread_anomaly"},
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


def test_structural_counter_normalizes_related_assets_and_edge_symbols() -> None:
    result = evaluate_structural_counter(
        signal={"signal_type": "momentum", "related_assets": [" rb ", "RB"]},
        context={},
        edges=[
            StructuralEdge(
                source_symbol="rb",
                target_symbol="hc",
                type="substitute",
                strength=0.7,
                propagation_direction=-1,
            )
        ],
    )

    assert result.passed is False
    assert result.sample_size == 1
    assert normalize_symbols([" rb ", "RB", " hc "]) == ["HC", "RB"]


def test_structural_lookup_statements_normalize_symbols_and_are_stable() -> None:
    node_id = uuid4()
    nodes_sql = _compile_postgres(structural_nodes_statement([" ru ", "RB", "RU"]))
    edges_sql = _compile_postgres(structural_edges_statement([node_id]))

    assert "commodity_nodes.symbol IN ('RB', 'RU')" in nodes_sql
    assert "ORDER BY commodity_nodes.symbol ASC, commodity_nodes.id ASC" in nodes_sql
    assert "relationship_edges.source IN" in edges_sql
    assert "relationship_edges.target IN" in edges_sql
    assert "ORDER BY relationship_edges.strength DESC, relationship_edges.id ASC" in edges_sql


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
    assert decision.passed is True
    assert decision.confidence_multiplier == 1.0
    assert round(decision.adjusted_signal["confidence"], 2) == 0.8
    assert decision.to_payload()["runtime_mode"] == "warmup"
    assert decision.to_payload()["warmup_enabled"] is True


def test_enforcing_failure_penalizes_signal_when_warmup_is_disabled() -> None:
    decision = decide_adversarial_outcome(
        signal={"signal_type": "spread_anomaly", "confidence": 0.8},
        signal_combination_hash="hash",
        results=[
            AdversarialCheckResult("null_hypothesis", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("historical_combo", passed=True, mode=MODE_INFORMATIONAL),
            AdversarialCheckResult("structural_counter", passed=True, mode=MODE_ENFORCING),
        ],
        runtime_mode="enforcing",
        warmup_enabled=False,
    )

    assert decision.passed is False
    assert decision.suppressed is False
    assert decision.confidence_multiplier == 0.7
    assert round(decision.adjusted_signal["confidence"], 2) == 0.56


def test_all_enforcing_failures_suppress_signal() -> None:
    decision = decide_adversarial_outcome(
        signal={"signal_type": "spread_anomaly", "confidence": 0.8},
        signal_combination_hash="hash",
        results=[
            AdversarialCheckResult("null_hypothesis", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("historical_combo", passed=False, mode=MODE_ENFORCING),
            AdversarialCheckResult("structural_counter", passed=False, mode=MODE_ENFORCING),
        ],
        runtime_mode="enforcing",
        warmup_enabled=False,
    )

    assert decision.suppressed is True
    assert decision.confidence_multiplier == 0.0


def _compile_postgres(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
