from app.services.learning.drift_monitor import (
    calculate_psi,
    correlation_matrix_from_returns,
    correlation_structure_drift,
    drift_severity,
    feature_distribution_drift,
    frobenius_distance,
    regime_switch_count,
    regime_switching_drift,
    signal_hit_rate_drift,
)


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
