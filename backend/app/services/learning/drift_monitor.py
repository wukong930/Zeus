from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import log, sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drift_metrics import DriftMetric
from app.models.regime_state import RegimeState
from app.models.signal import SignalTrack
from app.services.calibration.hit_rate import HIT_OUTCOMES, MISS_OUTCOMES, summarize_outcomes
from app.services.market_data.pit import get_market_data_pit
from app.services.signals.watchlist import WatchlistEntry, get_enabled_watchlist

EPSILON = 1e-6
RESOLVED_OUTCOMES = HIT_OUTCOMES | MISS_OUTCOMES


@dataclass(frozen=True)
class DriftMeasurement:
    metric_type: str
    feature_name: str
    psi: float
    drift_severity: str
    current_value: float
    baseline_value: float


@dataclass(frozen=True)
class DriftMonitorBatchResult:
    categories: int
    recorded: int
    skipped: int
    details: list[dict]


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


def correlation_structure_drift(
    *,
    baseline_matrix: list[list[float]],
    current_matrix: list[list[float]],
    feature_name: str = "correlation_matrix",
) -> DriftMeasurement:
    distance = frobenius_distance(baseline_matrix, current_matrix)
    return DriftMeasurement(
        metric_type="correlation_structure",
        feature_name=feature_name,
        psi=distance,
        drift_severity=threshold_severity(distance, yellow=0.25, red=0.5),
        current_value=distance,
        baseline_value=0.0,
    )


def signal_hit_rate_drift(
    *,
    baseline_hits: int,
    baseline_total: int,
    current_hits: int,
    current_total: int,
    feature_name: str = "hit_rate",
) -> DriftMeasurement:
    if baseline_total <= 0 or current_total <= 0:
        return DriftMeasurement(
            metric_type="signal_hit_rate",
            feature_name=feature_name,
            psi=0.0,
            drift_severity="green",
            current_value=0.0,
            baseline_value=0.0,
        )

    baseline_rate = baseline_hits / baseline_total
    current_rate = current_hits / current_total
    pooled_rate = (baseline_hits + current_hits) / (baseline_total + current_total)
    standard_error = sqrt(
        max(pooled_rate * (1 - pooled_rate), EPSILON)
        * (1 / baseline_total + 1 / current_total)
    )
    z_score = (current_rate - baseline_rate) / standard_error
    return DriftMeasurement(
        metric_type="signal_hit_rate",
        feature_name=feature_name,
        psi=abs(z_score),
        drift_severity=threshold_severity(z_score, yellow=1.0, red=2.0, absolute=True),
        current_value=current_rate,
        baseline_value=baseline_rate,
    )


def regime_switching_drift(
    regimes: list[str],
    *,
    max_monthly_switches: int = 3,
    feature_name: str = "monthly_switch_count",
) -> DriftMeasurement:
    switches = regime_switch_count(regimes)
    severity = "green"
    if switches > max_monthly_switches:
        severity = "red"
    elif switches == max_monthly_switches:
        severity = "yellow"

    return DriftMeasurement(
        metric_type="regime_switching",
        feature_name=feature_name,
        psi=float(switches),
        drift_severity=severity,
        current_value=float(switches),
        baseline_value=float(max_monthly_switches),
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


async def run_drift_monitor(
    session: AsyncSession,
    *,
    categories: list[str] | None = None,
    as_of: datetime | None = None,
    current_days: int = 30,
    baseline_days: int = 90,
    min_signal_samples: int = 1,
) -> DriftMonitorBatchResult:
    effective_as_of = as_of or datetime.now(timezone.utc)
    symbols_by_category, observed_categories = await _load_drift_scope(session)
    requested_categories = set(categories or observed_categories)

    details: list[dict] = []
    recorded = 0
    skipped = 0
    for category in sorted(requested_categories):
        category_symbols = symbols_by_category.get(category, [])
        feature_metrics = await record_feature_distribution_drifts(
            session,
            category=category,
            symbols=category_symbols,
            as_of=effective_as_of,
            current_days=current_days,
            baseline_days=baseline_days,
        )
        category_metrics = [
            await record_signal_hit_rate_drift(
                session,
                category=category,
                as_of=effective_as_of,
                current_days=current_days,
                baseline_days=baseline_days,
                min_samples=min_signal_samples,
            ),
            await record_regime_switching_drift(
                session,
                category=category,
                as_of=effective_as_of,
                window_days=current_days,
            ),
            await record_correlation_structure_drift(
                session,
                category=category,
                symbols=category_symbols,
                as_of=effective_as_of,
                current_days=current_days,
                baseline_days=baseline_days,
            ),
            *feature_metrics,
        ]

        for item in category_metrics:
            if item is None:
                skipped += 1
                details.append({"category": category, "status": "skipped"})
                continue

            recorded += 1
            details.append(
                {
                    "category": category,
                    "status": "recorded",
                    "metric_type": item.metric_type,
                    "feature_name": item.feature_name,
                    "severity": item.drift_severity,
                }
            )

    return DriftMonitorBatchResult(
        categories=len(requested_categories),
        recorded=recorded,
        skipped=skipped,
        details=details,
    )


async def record_signal_hit_rate_drift(
    session: AsyncSession,
    *,
    category: str,
    as_of: datetime | None = None,
    current_days: int = 30,
    baseline_days: int = 90,
    min_samples: int = 1,
) -> DriftMetric | None:
    effective_as_of = as_of or datetime.now(timezone.utc)
    current_start = effective_as_of - timedelta(days=current_days)
    baseline_start = current_start - timedelta(days=baseline_days)

    baseline_rows = await _load_signal_track_window(
        session,
        category=category,
        start=baseline_start,
        end=current_start,
    )
    current_rows = await _load_signal_track_window(
        session,
        category=category,
        start=current_start,
        end=effective_as_of,
    )
    baseline = summarize_outcomes(baseline_rows)
    current = summarize_outcomes(current_rows)
    if baseline.total < min_samples or current.total < min_samples:
        return None

    measurement = signal_hit_rate_drift(
        baseline_hits=baseline.hits,
        baseline_total=baseline.total,
        current_hits=current.hits,
        current_total=current.total,
    )
    return await record_drift_measurement(
        session,
        measurement,
        category=category,
        details={
            "baseline_total": baseline.total,
            "baseline_hits": baseline.hits,
            "current_total": current.total,
            "current_hits": current.hits,
            "current_days": current_days,
            "baseline_days": baseline_days,
        },
    )


async def record_regime_switching_drift(
    session: AsyncSession,
    *,
    category: str,
    as_of: datetime | None = None,
    window_days: int = 30,
    max_monthly_switches: int = 3,
) -> DriftMetric | None:
    effective_as_of = as_of or datetime.now(timezone.utc)
    since = (effective_as_of - timedelta(days=window_days)).date()
    rows = (
        await session.scalars(
            select(RegimeState)
            .where(
                RegimeState.category == category,
                RegimeState.as_of_date >= since,
                RegimeState.as_of_date <= effective_as_of.date(),
            )
            .order_by(RegimeState.as_of_date.asc())
        )
    ).all()
    if len(rows) < 2:
        return None

    measurement = regime_switching_drift(
        [row.regime for row in rows],
        max_monthly_switches=max_monthly_switches,
    )
    return await record_drift_measurement(
        session,
        measurement,
        category=category,
        details={
            "window_days": window_days,
            "states": [
                {"as_of_date": row.as_of_date.isoformat(), "regime": row.regime}
                for row in rows
            ],
        },
    )


async def record_correlation_structure_drift(
    session: AsyncSession,
    *,
    category: str,
    symbols: list[str],
    as_of: datetime | None = None,
    current_days: int = 30,
    baseline_days: int = 90,
) -> DriftMetric | None:
    effective_as_of = as_of or datetime.now(timezone.utc)
    unique_symbols = _unique_symbols(symbols)
    if len(unique_symbols) < 2:
        return None

    current_start = effective_as_of - timedelta(days=current_days)
    baseline_start = current_start - timedelta(days=baseline_days)
    baseline_returns = await _load_returns_by_symbol(
        session,
        symbols=unique_symbols,
        as_of=effective_as_of,
        start=baseline_start,
        end=current_start - timedelta(microseconds=1),
    )
    current_returns = await _load_returns_by_symbol(
        session,
        symbols=unique_symbols,
        as_of=effective_as_of,
        start=current_start,
        end=effective_as_of,
    )

    baseline_matrix, baseline_samples = correlation_matrix_from_returns(
        baseline_returns,
        symbols=unique_symbols,
    )
    current_matrix, current_samples = correlation_matrix_from_returns(
        current_returns,
        symbols=unique_symbols,
    )
    if baseline_matrix is None or current_matrix is None:
        return None

    measurement = correlation_structure_drift(
        baseline_matrix=baseline_matrix,
        current_matrix=current_matrix,
        feature_name="category_correlation_matrix",
    )
    return await record_drift_measurement(
        session,
        measurement,
        category=category,
        details={
            "symbols": unique_symbols,
            "baseline_samples": baseline_samples,
            "current_samples": current_samples,
            "baseline_days": baseline_days,
            "current_days": current_days,
            "baseline_matrix": baseline_matrix,
            "current_matrix": current_matrix,
        },
    )


async def record_feature_distribution_drifts(
    session: AsyncSession,
    *,
    category: str,
    symbols: list[str],
    as_of: datetime | None = None,
    current_days: int = 30,
    baseline_days: int = 90,
    min_samples: int = 5,
) -> list[DriftMetric]:
    effective_as_of = as_of or datetime.now(timezone.utc)
    unique_symbols = _unique_symbols(symbols)
    if not unique_symbols:
        return []

    current_start = effective_as_of - timedelta(days=current_days)
    baseline_start = current_start - timedelta(days=baseline_days)
    baseline_features: dict[str, list[float]] = {}
    current_features: dict[str, list[float]] = {}

    for symbol in unique_symbols:
        rows = await get_market_data_pit(
            session,
            symbol=symbol,
            as_of=effective_as_of,
            start=baseline_start,
            end=effective_as_of,
            limit=1000,
        )
        baseline_rows = [
            row for row in rows if baseline_start <= row.timestamp < current_start
        ]
        current_rows = [
            row for row in rows if current_start <= row.timestamp <= effective_as_of
        ]
        _merge_feature_values(baseline_features, market_feature_distributions(baseline_rows))
        _merge_feature_values(current_features, market_feature_distributions(current_rows))

    recorded: list[DriftMetric] = []
    for feature_name in sorted(set(baseline_features) | set(current_features)):
        baseline = baseline_features.get(feature_name, [])
        current = current_features.get(feature_name, [])
        if len(baseline) < min_samples or len(current) < min_samples:
            continue

        measurement = feature_distribution_drift(
            feature_name=feature_name,
            baseline=baseline,
            current=current,
        )
        recorded.append(
            await record_drift_measurement(
                session,
                measurement,
                category=category,
                details={
                    "symbols": unique_symbols,
                    "baseline_samples": len(baseline),
                    "current_samples": len(current),
                    "baseline_days": baseline_days,
                    "current_days": current_days,
                },
            )
        )

    return recorded


def threshold_severity(
    value: float,
    *,
    yellow: float,
    red: float,
    absolute: bool = False,
) -> str:
    score = abs(value) if absolute else value
    if score >= red:
        return "red"
    if score >= yellow:
        return "yellow"
    return "green"


def frobenius_distance(
    baseline_matrix: list[list[float]],
    current_matrix: list[list[float]],
) -> float:
    _validate_same_shape(baseline_matrix, current_matrix)
    total = 0.0
    for baseline_row, current_row in zip(baseline_matrix, current_matrix, strict=False):
        for baseline_value, current_value in zip(baseline_row, current_row, strict=False):
            total += (current_value - baseline_value) ** 2
    return sqrt(total)


def regime_switch_count(regimes: list[str]) -> int:
    switches = 0
    previous: str | None = None
    for regime in regimes:
        if not regime:
            continue
        if previous is not None and regime != previous:
            switches += 1
        previous = regime
    return switches


def correlation_matrix_from_returns(
    returns_by_symbol: dict[str, dict],
    *,
    symbols: list[str],
) -> tuple[list[list[float]] | None, int]:
    if len(symbols) < 2:
        return None, 0

    date_sets = [set(returns_by_symbol.get(symbol, {})) for symbol in symbols]
    if any(not dates for dates in date_sets):
        return None, 0

    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 2:
        return None, len(common_dates)

    aligned = {
        symbol: [returns_by_symbol[symbol][as_of_date] for as_of_date in common_dates]
        for symbol in symbols
    }
    matrix = [
        [_pearson(aligned[left], aligned[right]) for right in symbols]
        for left in symbols
    ]
    return matrix, len(common_dates)


def market_feature_distributions(rows: list) -> dict[str, list[float]]:
    ordered = sorted(rows, key=lambda row: row.timestamp)
    features: dict[str, list[float]] = {
        "daily_range_pct": [],
        "realized_volatility_proxy": [],
        "volume": [],
        "open_interest": [],
    }
    previous_close: float | None = None
    for row in ordered:
        close = float(row.close)
        if close != 0:
            features["daily_range_pct"].append((float(row.high) - float(row.low)) / abs(close))
        if previous_close is not None and previous_close != 0:
            features["realized_volatility_proxy"].append(
                abs((close - previous_close) / previous_close)
            )
        features["volume"].append(float(row.volume))
        if row.open_interest is not None:
            features["open_interest"].append(float(row.open_interest))
        previous_close = close

    return {name: values for name, values in features.items() if values}


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


def _merge_feature_values(
    target: dict[str, list[float]],
    source: dict[str, list[float]],
) -> None:
    for feature_name, values in source.items():
        target.setdefault(feature_name, []).extend(values)


async def _load_signal_track_window(
    session: AsyncSession,
    *,
    category: str,
    start: datetime,
    end: datetime,
) -> list[SignalTrack]:
    return list(
        (
            await session.scalars(
                select(SignalTrack)
                .where(
                    SignalTrack.category == category,
                    SignalTrack.created_at >= start,
                    SignalTrack.created_at < end,
                    SignalTrack.outcome.in_(RESOLVED_OUTCOMES),
                )
                .order_by(SignalTrack.created_at.asc())
            )
        ).all()
    )


async def _load_drift_scope(session: AsyncSession) -> tuple[dict[str, list[str]], set[str]]:
    watchlist = await get_enabled_watchlist(session)
    symbols_by_category = _symbols_by_category(watchlist)
    categories = set(symbols_by_category)
    categories.update((await session.scalars(select(SignalTrack.category).distinct())).all())
    categories.update((await session.scalars(select(RegimeState.category).distinct())).all())
    return symbols_by_category, categories


def _symbols_by_category(entries: list[WatchlistEntry]) -> dict[str, list[str]]:
    symbols_by_category: dict[str, list[str]] = {}
    for entry in entries:
        category_symbols = symbols_by_category.setdefault(entry.category, [])
        for symbol in entry.symbols:
            normalized = symbol.strip().upper()
            if normalized and normalized not in category_symbols:
                category_symbols.append(normalized)
    return symbols_by_category


async def _load_returns_by_symbol(
    session: AsyncSession,
    *,
    symbols: list[str],
    as_of: datetime,
    start: datetime,
    end: datetime,
) -> dict[str, dict]:
    returns_by_symbol: dict[str, dict] = {}
    for symbol in symbols:
        rows = await get_market_data_pit(
            session,
            symbol=symbol,
            as_of=as_of,
            start=start,
            end=end,
            limit=1000,
        )
        returns_by_symbol[symbol] = _daily_returns(rows)
    return returns_by_symbol


def _daily_returns(rows: list) -> dict:
    ordered = sorted(rows, key=lambda row: row.timestamp)
    returns: dict = {}
    previous_close: float | None = None
    for row in ordered:
        if previous_close is not None and previous_close != 0:
            returns[row.timestamp.date()] = (row.close - previous_close) / previous_close
        previous_close = row.close
    return returns


def _unique_symbols(symbols: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = symbol.strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _validate_same_shape(
    baseline_matrix: list[list[float]],
    current_matrix: list[list[float]],
) -> None:
    if not baseline_matrix or not current_matrix:
        raise ValueError("matrices must be non-empty")
    if len(baseline_matrix) != len(current_matrix):
        raise ValueError("matrices must have the same shape")
    for baseline_row, current_row in zip(baseline_matrix, current_matrix, strict=False):
        if len(baseline_row) != len(current_row):
            raise ValueError("matrices must have the same shape")


def _pearson(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0

    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=False)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = sqrt(left_variance * right_variance)
    if denominator <= 0:
        return 1.0 if left == right else 0.0
    return numerator / denominator
