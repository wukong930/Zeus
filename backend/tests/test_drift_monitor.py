from datetime import datetime, timezone
from uuid import uuid4

from app.api.drift import build_drift_notification, build_drift_snapshot
from app.models.drift_metrics import DriftMetric
from app.services.learning.drift_monitor import (
    calculate_psi,
    correlation_matrix_from_returns,
    correlation_structure_drift,
    drift_severity,
    feature_distribution_drift,
    frobenius_distance,
    market_feature_distributions,
    regime_switch_count,
    regime_switching_drift,
    signal_hit_rate_drift,
)


class MarketFeatureRow:
    def __init__(
        self,
        *,
        day: int,
        high: float,
        low: float,
        close: float,
        volume: float,
        open_interest: float | None,
    ) -> None:
        self.timestamp = day
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.open_interest = open_interest


def test_calculate_psi_is_small_for_matching_distributions() -> None:
    baseline = [float(value) for value in range(100)]
    current = [float(value) for value in range(100)]

    assert calculate_psi(baseline, current) == 0


def test_feature_distribution_drift_flags_shifted_distribution() -> None:
    baseline = [float(value) for value in range(100)]
    current = [float(value + 100) for value in range(100)]

    measurement = feature_distribution_drift(
        feature_name="volume",
        baseline=baseline,
        current=current,
    )

    assert measurement.metric_type == "feature_distribution"
    assert measurement.psi > 0.25
    assert measurement.drift_severity == "red"


def test_drift_severity_thresholds() -> None:
    assert drift_severity(0.05) == "green"
    assert drift_severity(0.15) == "yellow"
    assert drift_severity(0.25) == "red"


def test_correlation_structure_drift_flags_matrix_break() -> None:
    measurement = correlation_structure_drift(
        baseline_matrix=[[1.0, 0.8], [0.8, 1.0]],
        current_matrix=[[1.0, -0.2], [-0.2, 1.0]],
    )

    assert measurement.metric_type == "correlation_structure"
    assert measurement.psi == frobenius_distance(
        [[1.0, 0.8], [0.8, 1.0]],
        [[1.0, -0.2], [-0.2, 1.0]],
    )
    assert measurement.drift_severity == "red"


def test_signal_hit_rate_drift_uses_two_proportion_z_score() -> None:
    measurement = signal_hit_rate_drift(
        baseline_hits=80,
        baseline_total=100,
        current_hits=10,
        current_total=30,
    )

    assert measurement.metric_type == "signal_hit_rate"
    assert measurement.baseline_value == 0.8
    assert measurement.current_value == 10 / 30
    assert measurement.psi > 2
    assert measurement.drift_severity == "red"


def test_regime_switching_drift_counts_monthly_switches() -> None:
    regimes = ["range_low_vol", "trend_up_low_vol", "range_high_vol", "range_low_vol"]

    measurement = regime_switching_drift(regimes)

    assert regime_switch_count(regimes) == 3
    assert measurement.current_value == 3
    assert measurement.drift_severity == "yellow"
    assert regime_switching_drift([*regimes, "trend_down_low_vol"]).drift_severity == "red"


def test_correlation_matrix_from_returns_aligns_common_dates() -> None:
    returns = {
        "RB2601": {"d1": 0.01, "d2": 0.02, "d3": 0.03},
        "HC2601": {"d1": 0.02, "d2": 0.04, "d3": 0.06},
    }

    matrix, samples = correlation_matrix_from_returns(returns, symbols=["RB2601", "HC2601"])

    assert samples == 3
    assert matrix == [[1.0, 1.0], [1.0, 1.0]]


def test_market_feature_distributions_extracts_available_ohlcv_features() -> None:
    features = market_feature_distributions(
        [
            MarketFeatureRow(day=2, high=112, low=108, close=110, volume=1200, open_interest=None),
            MarketFeatureRow(day=1, high=105, low=95, close=100, volume=1000, open_interest=500),
        ]
    )

    assert features["daily_range_pct"] == [0.1, 4 / 110]
    assert features["realized_volatility_proxy"] == [0.1]
    assert features["volume"] == [1000.0, 1200.0]
    assert features["open_interest"] == [500.0]


def test_drift_snapshot_summarizes_highest_severity() -> None:
    rows = [
        DriftMetric(
            id=uuid4(),
            metric_type="feature_distribution",
            category="ferrous",
            feature_name="volume",
            current_value=0.22,
            baseline_value=0.1,
            psi=0.26,
            drift_severity="red",
            details={},
            computed_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        ),
        DriftMetric(
            id=uuid4(),
            metric_type="signal_hit_rate",
            category="rubber",
            feature_name=None,
            current_value=0.6,
            baseline_value=0.7,
            psi=0.12,
            drift_severity="yellow",
            details={},
            computed_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        ),
    ]

    snapshot = build_drift_snapshot(rows)

    assert snapshot.status == "red"
    assert snapshot.latest_at == datetime(2026, 5, 5, tzinfo=timezone.utc)
    assert snapshot.severity_counts["red"] == 1
    assert snapshot.severity_counts["yellow"] == 1
    assert snapshot.notification.level == "review"
    assert snapshot.notification.should_notify is True
    assert snapshot.notification.production_effect == "observe_only"
    assert snapshot.notification.top_metrics[0].drift_severity == "red"


def test_drift_notification_keeps_green_and_no_data_observe_only() -> None:
    green = build_drift_notification(
        [
            DriftMetric(
                id=uuid4(),
                metric_type="feature_distribution",
                category="ferrous",
                feature_name="volume",
                current_value=0.11,
                baseline_value=0.1,
                psi=0.03,
                drift_severity="green",
                details={},
                computed_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
            )
        ],
        status="green",
    )
    no_data = build_drift_notification([], status="no_data")

    assert green.should_notify is False
    assert green.production_effect == "observe_only"
    assert green.next_actions == ["保持监控，不自动修改生产阈值"]
    assert no_data.level == "no_data"
    assert no_data.should_notify is False
