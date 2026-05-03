from app.services.learning.drift_monitor import (
    calculate_psi,
    drift_severity,
    feature_distribution_drift,
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
