from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration import SignalCalibration
from app.models.signal import SignalTrack
from app.services.calibration.updater import (
    RESOLVED_OUTCOMES,
    CalibrationProposal,
    build_calibration_proposal,
)

DEFAULT_CONFIDENCE_LEVEL = 0.90
PRIOR_DOMINANT_SAMPLE_THRESHOLD = 10


@dataclass(frozen=True)
class CalibrationDashboardRow:
    signal_type: str
    category: str
    regime: str
    source: str
    sample_size: int
    hit_count: int
    miss_count: int
    rolling_hit_rate: float | None
    posterior_mean: float
    confidence_low: float
    confidence_high: float
    base_weight: float
    effective_weight: float
    alpha_prior: float
    beta_prior: float
    prior_dominant: bool
    decay_detected: bool
    computed_at: str | None
    effective_from: str | None

    @property
    def target_key(self) -> str:
        return f"{self.signal_type}:{self.category}:{self.regime}"

    def to_dict(self) -> dict:
        return {
            "target_key": self.target_key,
            "signal_type": self.signal_type,
            "category": self.category,
            "regime": self.regime,
            "source": self.source,
            "sample_size": self.sample_size,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "rolling_hit_rate": self.rolling_hit_rate,
            "posterior_mean": self.posterior_mean,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "base_weight": self.base_weight,
            "effective_weight": self.effective_weight,
            "alpha_prior": self.alpha_prior,
            "beta_prior": self.beta_prior,
            "prior_dominant": self.prior_dominant,
            "decay_detected": self.decay_detected,
            "computed_at": self.computed_at,
            "effective_from": self.effective_from,
        }


@dataclass(frozen=True)
class CalibrationDashboard:
    generated_at: str
    lookback_days: int
    confidence_level: float
    total_buckets: int
    mature_buckets: int
    prior_dominant_buckets: int
    decay_buckets: int
    sample_size: int
    avg_effective_weight: float | None
    rows: list[CalibrationDashboardRow]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "lookback_days": self.lookback_days,
            "confidence_level": self.confidence_level,
            "total_buckets": self.total_buckets,
            "mature_buckets": self.mature_buckets,
            "prior_dominant_buckets": self.prior_dominant_buckets,
            "decay_buckets": self.decay_buckets,
            "sample_size": self.sample_size,
            "avg_effective_weight": self.avg_effective_weight,
            "rows": [row.to_dict() for row in self.rows],
            "notes": self.notes,
        }


async def summarize_calibration_dashboard(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 180,
    min_samples: int = 1,
    limit: int = 100,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> CalibrationDashboard:
    effective_as_of = as_of or datetime.now(timezone.utc)
    since = effective_as_of - timedelta(days=lookback_days)

    active_calibrations = (
        await session.scalars(
            select(SignalCalibration)
            .where(
                SignalCalibration.effective_from <= effective_as_of,
                or_(
                    SignalCalibration.effective_to.is_(None),
                    SignalCalibration.effective_to > effective_as_of,
                ),
            )
            .order_by(desc(SignalCalibration.sample_size), desc(SignalCalibration.computed_at))
            .limit(limit)
        )
    ).all()
    rows = [
        calibration_row_to_dashboard_row(
            calibration,
            confidence_level=confidence_level,
        )
        for calibration in active_calibrations
    ]
    seen = {row.target_key for row in rows}

    resolved_tracks = (
        await session.scalars(
            select(SignalTrack)
            .where(
                SignalTrack.created_at >= since,
                SignalTrack.outcome.in_(RESOLVED_OUTCOMES),
            )
            .order_by(SignalTrack.created_at.desc())
            .limit(5000)
        )
    ).all()
    grouped_tracks: dict[tuple[str, str, str], list[SignalTrack]] = defaultdict(list)
    for track in resolved_tracks:
        key = (
            track.signal_type,
            track.category,
            track.regime_at_emission or track.regime or "unknown",
        )
        grouped_tracks[key].append(track)

    for (signal_type, category, regime), tracks in grouped_tracks.items():
        target_key = f"{signal_type}:{category}:{regime}"
        if target_key in seen or len(tracks) < min_samples:
            continue
        proposal = build_calibration_proposal(
            tracks,
            signal_type=signal_type,
            category=category,
            regime=regime,
        )
        rows.append(proposal_to_dashboard_row(proposal, confidence_level=confidence_level))
        seen.add(target_key)

    rows = sorted(
        rows,
        key=lambda row: (row.decay_detected, row.sample_size, row.effective_weight),
        reverse=True,
    )[:limit]
    notes = []
    if not rows:
        notes.append("No resolved calibration buckets are available yet.")
    if any(row.source == "candidate_from_tracks" for row in rows):
        notes.append("Some rows are recent resolved-signal candidates and are not active weights yet.")
    return CalibrationDashboard(
        generated_at=effective_as_of.isoformat(),
        lookback_days=lookback_days,
        confidence_level=confidence_level,
        total_buckets=len(rows),
        mature_buckets=sum(1 for row in rows if not row.prior_dominant),
        prior_dominant_buckets=sum(1 for row in rows if row.prior_dominant),
        decay_buckets=sum(1 for row in rows if row.decay_detected),
        sample_size=sum(row.sample_size for row in rows),
        avg_effective_weight=_avg([row.effective_weight for row in rows]),
        rows=rows,
        notes=notes,
    )


def calibration_row_to_dashboard_row(
    calibration: SignalCalibration,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> CalibrationDashboardRow:
    posterior_mean, low, high = posterior_band(
        hits=calibration.hit_count,
        misses=calibration.miss_count,
        alpha_prior=calibration.alpha_prior,
        beta_prior=calibration.beta_prior,
        confidence_level=confidence_level,
    )
    sample_size = calibration.hit_count + calibration.miss_count or calibration.sample_size
    hit_rate = calibration.rolling_hit_rate
    if hit_rate is None and sample_size > 0:
        hit_rate = calibration.hit_count / sample_size
    return CalibrationDashboardRow(
        signal_type=calibration.signal_type,
        category=calibration.category,
        regime=calibration.regime,
        source="active_calibration",
        sample_size=sample_size,
        hit_count=calibration.hit_count,
        miss_count=calibration.miss_count,
        rolling_hit_rate=hit_rate,
        posterior_mean=posterior_mean,
        confidence_low=low,
        confidence_high=high,
        base_weight=calibration.base_weight,
        effective_weight=calibration.effective_weight,
        alpha_prior=calibration.alpha_prior,
        beta_prior=calibration.beta_prior,
        prior_dominant=sample_size < PRIOR_DOMINANT_SAMPLE_THRESHOLD,
        decay_detected=calibration.decay_detected,
        computed_at=_iso(calibration.computed_at),
        effective_from=_iso(calibration.effective_from),
    )


def proposal_to_dashboard_row(
    proposal: CalibrationProposal,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> CalibrationDashboardRow:
    posterior_mean, low, high = posterior_band(
        hits=proposal.hit_count,
        misses=proposal.miss_count,
        alpha_prior=proposal.alpha_prior,
        beta_prior=proposal.beta_prior,
        confidence_level=confidence_level,
    )
    return CalibrationDashboardRow(
        signal_type=proposal.signal_type,
        category=proposal.category,
        regime=proposal.regime,
        source="candidate_from_tracks",
        sample_size=proposal.sample_size,
        hit_count=proposal.hit_count,
        miss_count=proposal.miss_count,
        rolling_hit_rate=proposal.rolling_hit_rate,
        posterior_mean=posterior_mean,
        confidence_low=low,
        confidence_high=high,
        base_weight=proposal.base_weight,
        effective_weight=proposal.effective_weight,
        alpha_prior=proposal.alpha_prior,
        beta_prior=proposal.beta_prior,
        prior_dominant=proposal.prior_dominant,
        decay_detected=proposal.decay_detected,
        computed_at=None,
        effective_from=None,
    )


def posterior_band(
    *,
    hits: int,
    misses: int,
    alpha_prior: float,
    beta_prior: float,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> tuple[float, float, float]:
    alpha = alpha_prior + max(hits, 0)
    beta = beta_prior + max(misses, 0)
    total = alpha + beta
    mean = alpha / total
    variance = (alpha * beta) / ((total**2) * (total + 1))
    z_score = 1.645 if confidence_level >= 0.9 else 1.28
    margin = z_score * (variance**0.5)
    return (
        round(mean, 4),
        round(max(0.0, mean - margin), 4),
        round(min(1.0, mean + margin), 4),
    )


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
