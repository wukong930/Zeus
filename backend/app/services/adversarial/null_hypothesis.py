from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import erfc, sqrt
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.null_distribution_cache import NullDistributionCache
from app.models.signal import SignalTrack
from app.services.adversarial.types import AdversarialCheckResult

DEFAULT_NULL_STATS = {
    "mean": 1.0,
    "std_dev": 0.5,
    "p95": 1.96,
    "samples": [0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 1.96],
}


@dataclass(frozen=True)
class NullDistributionSummary:
    signal_type: str
    category: str
    computed_for: date
    sample_size: int
    distribution_stats: dict[str, Any]


def signal_strength_statistic(signal: dict[str, Any]) -> float:
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("z_score") is not None:
        return abs(float(spread_info["z_score"]))
    if signal.get("z_score") is not None:
        return abs(float(signal["z_score"]))
    return abs(float(signal.get("confidence", 0))) * 3


def estimate_pvalue(statistic: float, distribution_stats: dict[str, Any]) -> float:
    samples = [float(value) for value in distribution_stats.get("samples", [])]
    if samples:
        exceedances = sum(1 for value in samples if value >= statistic)
        if exceedances == 0:
            return min(0.01, 1 / (len(samples) + 1))
        return (exceedances + 1) / (len(samples) + 1)

    std_dev = float(distribution_stats.get("std_dev") or DEFAULT_NULL_STATS["std_dev"])
    average = float(distribution_stats.get("mean") or DEFAULT_NULL_STATS["mean"])
    if std_dev <= 0:
        return 0.0 if statistic > average else 1.0

    z_score = (statistic - average) / std_dev
    return erfc(z_score / sqrt(2)) / 2


def evaluate_null_hypothesis(
    signal: dict[str, Any],
    cache: NullDistributionCache | NullDistributionSummary | None = None,
    *,
    pvalue_threshold: float = 0.05,
) -> AdversarialCheckResult:
    statistic = signal_strength_statistic(signal)
    distribution_stats = _distribution_stats(cache)
    threshold = _pvalue_threshold(cache, default=pvalue_threshold)
    pvalue = estimate_pvalue(statistic, distribution_stats)
    passed = pvalue < threshold
    return AdversarialCheckResult(
        check_name="null_hypothesis",
        passed=passed,
        score=pvalue,
        sample_size=int(distribution_stats.get("sample_size") or _sample_size(cache)),
        reason=(
            f"Signal statistic {statistic:.4f} has p-value {pvalue:.4f} "
            f"against cached null distribution."
        ),
        details={
            "statistic": statistic,
            "pvalue": pvalue,
            "pvalue_threshold": threshold,
            "distribution_stats": distribution_stats,
        },
    )


async def latest_null_distribution_cache(
    session: AsyncSession,
    *,
    signal_type: str,
    category: str,
    as_of: datetime | None = None,
) -> NullDistributionCache | None:
    effective_as_of = as_of or datetime.now(timezone.utc)
    return (
        await session.scalars(
            select(NullDistributionCache)
            .where(
                NullDistributionCache.signal_type == signal_type,
                NullDistributionCache.category == category,
                NullDistributionCache.computed_for <= effective_as_of.date(),
            )
            .order_by(desc(NullDistributionCache.computed_for))
            .limit(1)
        )
    ).first()


async def precompute_all_null_distributions(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 90,
) -> list[NullDistributionCache]:
    effective_as_of = as_of or datetime.now(timezone.utc)
    since = effective_as_of - timedelta(days=lookback_days)
    rows = (
        await session.scalars(
            select(SignalTrack)
            .where(SignalTrack.created_at >= since)
            .order_by(SignalTrack.created_at.asc())
        )
    ).all()

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row.signal_type, row.category)].append(signal_track_statistic(row))

    caches: list[NullDistributionCache] = []
    for (signal_type, category), values in grouped.items():
        summary = summarize_null_distribution(
            values,
            signal_type=signal_type,
            category=category,
            computed_for=effective_as_of.date(),
        )
        caches.append(await upsert_null_distribution_cache(session, summary))

    return caches


def summarize_null_distribution(
    values: list[float],
    *,
    signal_type: str,
    category: str,
    computed_for: date,
) -> NullDistributionSummary:
    ordered = sorted(float(value) for value in values)
    stats = DEFAULT_NULL_STATS.copy()
    if ordered:
        stats = {
            "mean": mean(ordered),
            "std_dev": pstdev(ordered) if len(ordered) > 1 else 0.0,
            "p95": percentile(ordered, 95),
            "samples": ordered[-200:],
            "sample_size": len(ordered),
        }

    return NullDistributionSummary(
        signal_type=signal_type,
        category=category,
        computed_for=computed_for,
        sample_size=len(ordered),
        distribution_stats=stats,
    )


async def upsert_null_distribution_cache(
    session: AsyncSession,
    summary: NullDistributionSummary,
) -> NullDistributionCache:
    row = (
        await session.scalars(
            select(NullDistributionCache)
            .where(
                NullDistributionCache.signal_type == summary.signal_type,
                NullDistributionCache.category == summary.category,
                NullDistributionCache.computed_for == summary.computed_for,
            )
            .limit(1)
        )
    ).first()
    if row is None:
        row = NullDistributionCache(
            signal_type=summary.signal_type,
            category=summary.category,
            computed_for=summary.computed_for,
        )
        session.add(row)

    row.sample_size = summary.sample_size
    row.statistic_name = "signal_strength"
    row.distribution_stats = {
        **summary.distribution_stats,
        "sample_size": summary.sample_size,
    }
    row.computed_at = datetime.now(timezone.utc)
    await session.flush()
    return row


def signal_track_statistic(row: SignalTrack) -> float:
    if row.z_score is not None:
        return abs(row.z_score)
    return abs(row.confidence) * 3


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    index = round((len(values) - 1) * percentile_value / 100)
    return values[index]


def _distribution_stats(
    cache: NullDistributionCache | NullDistributionSummary | None,
) -> dict[str, Any]:
    if cache is None:
        return DEFAULT_NULL_STATS
    stats = dict(cache.distribution_stats or {})
    stats.setdefault("sample_size", _sample_size(cache))
    return stats


def _sample_size(cache: NullDistributionCache | NullDistributionSummary | None) -> int:
    if cache is None:
        return len(DEFAULT_NULL_STATS["samples"])
    return int(cache.sample_size or 0)


def _pvalue_threshold(
    cache: NullDistributionCache | NullDistributionSummary | None,
    *,
    default: float,
) -> float:
    if isinstance(cache, NullDistributionCache):
        return cache.pvalue_threshold
    return default
