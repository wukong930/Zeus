from dataclasses import dataclass
from math import log

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drift_metrics import DriftMetric

EPSILON = 1e-6


@dataclass(frozen=True)
class DriftMeasurement:
    metric_type: str
    feature_name: str
    psi: float
    drift_severity: str
    current_value: float
    baseline_value: float


def calculate_psi(
    baseline: list[float],
    current: list[float],
    *,
    buckets: int = 10,
) -> float:
    if not baseline or not current:
        return 0.0
    if buckets <= 0:
        raise ValueError("buckets must be positive")

    sorted_baseline = sorted(baseline)
    edges = _quantile_edges(sorted_baseline, buckets)
    if len(set(edges)) < 2:
        return 0.0

    baseline_counts = _bucket_counts(baseline, edges)
    current_counts = _bucket_counts(current, edges)
    baseline_total = sum(baseline_counts)
    current_total = sum(current_counts)
    psi = 0.0

    for baseline_count, current_count in zip(baseline_counts, current_counts, strict=False):
        expected = max(baseline_count / baseline_total, EPSILON)
        actual = max(current_count / current_total, EPSILON)
        psi += (actual - expected) * log(actual / expected)

    return psi


def feature_distribution_drift(
    *,
    feature_name: str,
    baseline: list[float],
    current: list[float],
) -> DriftMeasurement:
    psi = calculate_psi(baseline, current)
    return DriftMeasurement(
        metric_type="feature_distribution",
        feature_name=feature_name,
        psi=psi,
        drift_severity=drift_severity(psi),
        current_value=sum(current) / len(current) if current else 0,
        baseline_value=sum(baseline) / len(baseline) if baseline else 0,
    )


def drift_severity(psi: float) -> str:
    if psi >= 0.25:
        return "red"
    if psi >= 0.1:
        return "yellow"
    return "green"


async def record_drift_measurement(
    session: AsyncSession,
    measurement: DriftMeasurement,
    *,
    category: str | None = None,
    details: dict | None = None,
) -> DriftMetric:
    row = DriftMetric(
        metric_type=measurement.metric_type,
        category=category,
        feature_name=measurement.feature_name,
        current_value=measurement.current_value,
        baseline_value=measurement.baseline_value,
        psi=measurement.psi,
        drift_severity=measurement.drift_severity,
        details=details or {},
    )
    session.add(row)
    await session.flush()
    return row


def _quantile_edges(values: list[float], buckets: int) -> list[float]:
    edges = [values[0]]
    max_index = len(values) - 1
    for bucket in range(1, buckets):
        index = round(max_index * bucket / buckets)
        edges.append(values[index])
    edges.append(values[-1])
    return edges


def _bucket_counts(values: list[float], edges: list[float]) -> list[int]:
    counts = [0 for _ in range(len(edges) - 1)]
    for value in values:
        if value < edges[0]:
            counts[0] += 1
            continue
        if value > edges[-1]:
            counts[-1] += 1
            continue
        for idx in range(len(edges) - 1):
            lower = edges[idx]
            upper = edges[idx + 1]
            is_last = idx == len(edges) - 2
            if lower <= value < upper or (is_last and lower <= value <= upper):
                counts[idx] += 1
                break
    return counts
