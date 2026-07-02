from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.models.signal import SignalTrack
from app.services.calibration.hit_rate import (
    summarize_outcomes,
    summarize_outcomes_by_semantics,
)
from app.services.calibration.tracker import (
    _active_calibration_statement,
    signal_combination_hash,
    track_signal_emission,
)
from app.services.calibration.weight_adjuster import calculate_bayesian_weight


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


def test_bayesian_weight_stays_at_base_during_cold_start() -> None:
    result = calculate_bayesian_weight(hits=0, total=0, base_weight=1.0)

    assert result.posterior_mean == 0.5
    assert result.effective_weight == 1.0
    assert result.prior_dominant is True


def test_bayesian_weight_uses_hits_and_total() -> None:
    result = calculate_bayesian_weight(hits=140, total=200, base_weight=1.0)

    assert round(result.posterior_mean, 3) == 0.692
    assert round(result.effective_weight, 3) == 1.385
    assert result.sample_size == 200
    assert result.miss_count == 60


def test_signal_combination_hash_is_order_insensitive_for_assets() -> None:
    first = signal_combination_hash(
        signal_type="spread_anomaly",
        category="ferrous",
        regime="range_low_vol",
        related_assets=["RB", "HC"],
    )
    second = signal_combination_hash(
        signal_type="spread_anomaly",
        category="ferrous",
        regime="range_low_vol",
        related_assets=["HC", "RB"],
    )

    assert first == second
    assert len(first) == 64


def test_signal_combination_hash_normalizes_scope_and_assets() -> None:
    first = signal_combination_hash(
        signal_type=" Spread_Anomaly ",
        category=" Ferrous ",
        regime=" Range_Low_Vol ",
        related_assets=[" rb ", "HC", "RB", ""],
    )
    second = signal_combination_hash(
        signal_type="spread_anomaly",
        category="ferrous",
        regime="range_low_vol",
        related_assets=["HC", "RB"],
    )

    assert first == second


def test_active_calibration_statement_is_point_in_time_and_stable() -> None:
    sql = _compile_postgres(
        _active_calibration_statement(
            signal_type="momentum",
            category="energy",
            regime="range_low_vol",
            as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
        )
    )

    assert "signal_calibration.signal_type =" in sql
    assert "signal_calibration.category =" in sql
    assert "signal_calibration.regime =" in sql
    assert "signal_calibration.effective_from <=" in sql
    assert "signal_calibration.effective_to IS NULL" in sql
    assert (
        "ORDER BY signal_calibration.effective_from DESC, "
        "signal_calibration.computed_at DESC, signal_calibration.id DESC"
    ) in sql
    assert "LIMIT" in sql


async def test_track_signal_emission_records_calibration_metadata() -> None:
    session = FakeSession()

    row = await track_signal_emission(
        session,  # type: ignore[arg-type]
        signal={
            "signal_type": "spread_anomaly",
            "confidence": 0.8,
            "related_assets": ["RB", "HC"],
            "spread_info": {"z_score": 2.8},
        },
        category="ferrous",
        regime="range_low_vol",
        calibration_weight=1.2,
    )

    assert row is session.rows[0]
    assert row.calibration_weight_at_emission == 1.2
    assert row.regime_at_emission == "range_low_vol"
    assert row.direction is None
    assert row.signal_combination_hash is not None
    assert session.flush_count == 1


async def test_track_signal_emission_persists_structured_direction() -> None:
    session = FakeSession()

    row = await track_signal_emission(
        session,  # type: ignore[arg-type]
        signal={
            "signal_type": "momentum",
            "confidence": 0.86,
            "direction": "bearish",
            "related_assets": ["RB"],
        },
        category="ferrous",
        regime="downtrend",
        calibration_weight=1.0,
    )

    assert row is session.rows[0]
    assert row.direction == "bearish"


def test_summarize_outcomes_counts_hit_and_miss_only() -> None:
    rows = [
        SignalTrack(
            signal_type="momentum",
            category="energy",
            confidence=0.7,
            outcome="hit",
            created_at=datetime.now(timezone.utc),
        ),
        SignalTrack(
            signal_type="momentum",
            category="energy",
            confidence=0.7,
            outcome="miss",
            created_at=datetime.now(timezone.utc),
        ),
        SignalTrack(
            signal_type="momentum",
            category="energy",
            confidence=0.7,
            outcome="pending",
            created_at=datetime.now(timezone.utc),
        ),
    ]

    summary = summarize_outcomes(rows)

    assert summary.hits == 1
    assert summary.misses == 1
    assert summary.total == 2
    assert summary.hit_rate == 0.5


def _track(signal_type: str, outcome: str) -> SignalTrack:
    return SignalTrack(
        signal_type=signal_type,
        category="ferrous",
        confidence=0.7,
        outcome=outcome,
        created_at=datetime.now(timezone.utc),
    )


def test_summarize_outcomes_by_semantics_does_not_blend_classes() -> None:
    rows = [
        _track("momentum", "hit"),  # directional
        _track("momentum", "miss"),  # directional
        _track("spread_anomaly", "hit"),  # mean_reversion
        _track("regime_shift", "miss"),  # volatility
    ]

    # The pooled number hides the split: 2/4 = 50% overall...
    assert summarize_outcomes(rows).hit_rate == 0.5

    # ...while the honest breakdown shows a 100% mean-reversion and a 0% volatility
    # bucket that the pooled figure blended away.
    by_sem = summarize_outcomes_by_semantics(rows)
    assert by_sem["directional"].hits == 1 and by_sem["directional"].total == 2
    assert by_sem["directional"].hit_rate == 0.5
    assert by_sem["mean_reversion"].hit_rate == 1.0
    assert by_sem["volatility"].hit_rate == 0.0
    assert by_sem["volatility"].hits == 0 and by_sem["volatility"].total == 1


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
