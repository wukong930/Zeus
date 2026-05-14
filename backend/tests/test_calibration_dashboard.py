from datetime import datetime, timedelta, timezone

from app.models.calibration import SignalCalibration
from app.models.signal import SignalTrack
from app.services.calibration.dashboard import (
    posterior_band,
    summarize_calibration_dashboard,
)


class FakeScalars:
    def __init__(self, rows: list | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list:
        return self._rows


class FakeSession:
    def __init__(self, scalar_rows: list[list]) -> None:
        self.scalar_rows = scalar_rows
        self.calls = 0

    async def scalars(self, _) -> FakeScalars:
        rows = self.scalar_rows[self.calls] if self.calls < len(self.scalar_rows) else []
        self.calls += 1
        return FakeScalars(rows)


def test_posterior_band_uses_prior_and_observed_outcomes() -> None:
    mean, low, high = posterior_band(hits=8, misses=2, alpha_prior=4, beta_prior=4)

    assert mean == 0.6667
    assert low < mean < high
    assert 0 <= low <= 1
    assert 0 <= high <= 1


async def test_calibration_dashboard_merges_active_weights_and_candidate_groups() -> None:
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    active = SignalCalibration(
        signal_type="momentum",
        category="ferrous",
        regime="range_low_vol",
        base_weight=1.0,
        effective_weight=1.25,
        rolling_hit_rate=0.7,
        sample_size=10,
        hit_count=7,
        miss_count=3,
        alpha_prior=4.0,
        beta_prior=4.0,
        decay_detected=False,
        effective_from=now - timedelta(days=1),
        computed_at=now,
    )
    tracks = [
        _track("hit", "basis_shift", "rubber", "range_high_vol", now),
        _track("miss", "basis_shift", "rubber", "range_high_vol", now),
        _track("hit", "basis_shift", "rubber", "range_high_vol", now),
        _track("hit", "momentum", "ferrous", "range_low_vol", now),
    ]
    session = FakeSession([[active], tracks])

    dashboard = await summarize_calibration_dashboard(
        session,  # type: ignore[arg-type]
        as_of=now,
        min_samples=1,
    )
    rows = {row.target_key: row for row in dashboard.rows}

    assert dashboard.total_buckets == 2
    assert dashboard.sample_size == 13
    assert rows["momentum:ferrous:range_low_vol"].source == "active_calibration"
    assert rows["momentum:ferrous:range_low_vol"].effective_weight == 1.25
    assert rows["momentum:ferrous:range_low_vol"].prior_dominant is False
    assert rows["basis_shift:rubber:range_high_vol"].source == "candidate_from_tracks"
    assert rows["basis_shift:rubber:range_high_vol"].sample_size == 3
    assert rows["basis_shift:rubber:range_high_vol"].prior_dominant is True
    assert dashboard.prior_dominant_buckets == 1
    assert dashboard.mature_buckets == 1
    assert dashboard.notes == [
        "Some rows are recent resolved-signal candidates and are not active weights yet."
    ]


async def test_calibration_dashboard_returns_empty_runtime_state() -> None:
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    dashboard = await summarize_calibration_dashboard(
        FakeSession([[], []]),  # type: ignore[arg-type]
        as_of=now,
    )

    assert dashboard.total_buckets == 0
    assert dashboard.avg_effective_weight is None
    assert dashboard.rows == []
    assert dashboard.notes == ["No resolved calibration buckets are available yet."]


def _track(
    outcome: str,
    signal_type: str,
    category: str,
    regime: str,
    created_at: datetime,
) -> SignalTrack:
    return SignalTrack(
        signal_type=signal_type,
        category=category,
        confidence=0.72,
        outcome=outcome,
        regime_at_emission=regime,
        created_at=created_at,
    )
