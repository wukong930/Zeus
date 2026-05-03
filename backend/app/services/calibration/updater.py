from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration import SignalCalibration
from app.models.signal import SignalTrack
from app.services.calibration.decay_detector import detect_decay
from app.services.calibration.hit_rate import summarize_outcomes
from app.services.calibration.weight_adjuster import calculate_bayesian_weight
from app.services.governance.review_queue import ReviewRequiredError, enqueue_review, review_required

RESOLVED_OUTCOMES = {"hit", "miss", "success", "failure", "win", "loss"}


@dataclass(frozen=True)
class CalibrationProposal:
    signal_type: str
    category: str
    regime: str
    base_weight: float
    effective_weight: float
    rolling_hit_rate: float | None
    sample_size: int
    hit_count: int
    miss_count: int
    alpha_prior: float
    beta_prior: float
    decay_detected: bool
    decay_score: float
    prior_dominant: bool

    @property
    def target_key(self) -> str:
        return f"{self.signal_type}:{self.category}:{self.regime}"

    def to_change(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationReviewResult:
    groups: int
    queued: int
    skipped: int


def build_calibration_proposal(
    rows: list[SignalTrack],
    *,
    signal_type: str,
    category: str,
    regime: str,
    existing: SignalCalibration | None = None,
) -> CalibrationProposal:
    summary = summarize_outcomes(rows)
    base_weight = existing.base_weight if existing is not None else 1.0
    alpha_prior = existing.alpha_prior if existing is not None else 4.0
    beta_prior = existing.beta_prior if existing is not None else 4.0
    decay = detect_decay(rows, baseline_hit_rate=summary.hit_rate or 0.5)
    weight = calculate_bayesian_weight(
        hits=summary.hits,
        total=summary.total,
        base_weight=base_weight,
        alpha_prior=alpha_prior,
        beta_prior=beta_prior,
        decay_detected=decay.decay_detected,
    )

    return CalibrationProposal(
        signal_type=signal_type,
        category=category,
        regime=regime,
        base_weight=base_weight,
        effective_weight=weight.effective_weight,
        rolling_hit_rate=summary.hit_rate,
        sample_size=summary.total,
        hit_count=summary.hits,
        miss_count=summary.misses,
        alpha_prior=alpha_prior,
        beta_prior=beta_prior,
        decay_detected=decay.decay_detected,
        decay_score=decay.cusum_score,
        prior_dominant=weight.prior_dominant,
    )


async def generate_calibration_reviews(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 90,
    min_samples: int = 1,
) -> CalibrationReviewResult:
    effective_as_of = as_of or datetime.now(timezone.utc)
    since = effective_as_of - timedelta(days=lookback_days)
    rows = (
        await session.scalars(
            select(SignalTrack)
            .where(
                SignalTrack.created_at >= since,
                SignalTrack.outcome.in_(RESOLVED_OUTCOMES),
            )
            .order_by(SignalTrack.created_at.asc())
        )
    ).all()

    groups: dict[tuple[str, str, str], list[SignalTrack]] = defaultdict(list)
    for row in rows:
        groups[
            (
                row.signal_type,
                row.category,
                row.regime_at_emission or row.regime or "unknown",
            )
        ].append(row)

    queued = 0
    skipped = 0
    for (signal_type, category, regime), group_rows in groups.items():
        if len(group_rows) < min_samples:
            skipped += 1
            continue

        existing = await get_active_calibration(
            session,
            signal_type=signal_type,
            category=category,
            regime=regime,
            as_of=effective_as_of,
        )
        proposal = build_calibration_proposal(
            group_rows,
            signal_type=signal_type,
            category=category,
            regime=regime,
            existing=existing,
        )
        await enqueue_review(
            session,
            source="calibration",
            target_table="signal_calibration",
            target_key=proposal.target_key,
            proposed_change=proposal.to_change(),
            reason="Bayesian calibration proposal from shadow outcomes.",
        )
        queued += 1

    return CalibrationReviewResult(groups=len(groups), queued=queued, skipped=skipped)


async def get_active_calibration(
    session: AsyncSession,
    *,
    signal_type: str,
    category: str,
    regime: str,
    as_of: datetime,
) -> SignalCalibration | None:
    return (
        await session.scalars(
            select(SignalCalibration)
            .where(
                SignalCalibration.signal_type == signal_type,
                SignalCalibration.category == category,
                SignalCalibration.regime == regime,
                SignalCalibration.effective_from <= as_of,
                or_(
                    SignalCalibration.effective_to.is_(None),
                    SignalCalibration.effective_to > as_of,
                ),
            )
            .order_by(desc(SignalCalibration.effective_from))
            .limit(1)
        )
    ).first()


@review_required("signal_calibration")
async def apply_signal_calibration_change(
    session: AsyncSession,
    proposal: CalibrationProposal,
    *,
    applied_at: datetime | None = None,
) -> SignalCalibration:
    effective_at = applied_at or datetime.now(timezone.utc)
    existing = await get_active_calibration(
        session,
        signal_type=proposal.signal_type,
        category=proposal.category,
        regime=proposal.regime,
        as_of=effective_at,
    )
    if existing is not None:
        existing.effective_to = effective_at

    row = SignalCalibration(
        signal_type=proposal.signal_type,
        category=proposal.category,
        regime=proposal.regime,
        base_weight=proposal.base_weight,
        effective_weight=proposal.effective_weight,
        rolling_hit_rate=proposal.rolling_hit_rate,
        sample_size=proposal.sample_size,
        hit_count=proposal.hit_count,
        miss_count=proposal.miss_count,
        alpha_prior=proposal.alpha_prior,
        beta_prior=proposal.beta_prior,
        decay_detected=proposal.decay_detected,
        effective_from=effective_at,
        computed_at=effective_at,
    )
    session.add(row)
    await session.flush()
    return row


async def try_apply_without_review(
    session: AsyncSession,
    proposal: CalibrationProposal,
) -> None:
    try:
        await apply_signal_calibration_change(
            session,
            proposal,
            proposed_change=proposal.to_change(),
            review_source="calibration",
            target_key=proposal.target_key,
        )
    except ReviewRequiredError:
        return
