from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import SignalTrack
from app.services.alert_agent.config import ConfidenceThresholds, load_confidence_thresholds
from app.services.calibration.hit_rate import HIT_OUTCOMES, MISS_OUTCOMES
from app.services.governance.review_queue import enqueue_review

RESOLVED_OUTCOMES = HIT_OUTCOMES | MISS_OUTCOMES


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    samples: int
    avg_confidence: float | None
    hit_rate: float | None
    calibration_gap: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IsotonicPoint:
    confidence: float
    calibrated_probability: float
    samples: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThresholdCalibrationReport:
    signal_type: str | None
    category: str | None
    samples: int
    hits: int
    misses: int
    brier_score: float | None
    expected_calibration_error: float | None
    projected_calibration_error: float | None
    calibration_error_improvement: float | None
    bins: list[ReliabilityBin]
    isotonic_curve: list[IsotonicPoint]
    current_thresholds: dict[str, float]
    suggested_thresholds: dict[str, float]
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bins"] = [item.to_dict() for item in self.bins]
        payload["isotonic_curve"] = [item.to_dict() for item in self.isotonic_curve]
        return payload


async def generate_threshold_calibration_report(
    session: AsyncSession,
    *,
    signal_type: str | None = None,
    category: str | None = None,
    as_of: datetime | None = None,
    lookback_days: int = 180,
    bins: int = 10,
    min_samples: int = 20,
    target_auto_hit_rate: float = 0.75,
    target_notify_hit_rate: float = 0.55,
) -> ThresholdCalibrationReport:
    effective_at = as_of or datetime.now(timezone.utc)
    since = effective_at - timedelta(days=lookback_days)
    statement = select(SignalTrack).where(
        SignalTrack.created_at >= since,
        SignalTrack.created_at <= effective_at,
        SignalTrack.outcome.in_(RESOLVED_OUTCOMES),
    )
    if signal_type is not None:
        statement = statement.where(SignalTrack.signal_type == signal_type)
    if category is not None:
        statement = statement.where(SignalTrack.category == category)
    rows = list((await session.scalars(statement.order_by(SignalTrack.created_at.asc()))).all())
    current = await load_confidence_thresholds(session)
    return build_threshold_calibration_report(
        rows,
        signal_type=signal_type,
        category=category,
        current_thresholds=current,
        bins=bins,
        min_samples=min_samples,
        target_auto_hit_rate=target_auto_hit_rate,
        target_notify_hit_rate=target_notify_hit_rate,
    )


def build_threshold_calibration_report(
    rows: list[SignalTrack],
    *,
    signal_type: str | None = None,
    category: str | None = None,
    current_thresholds: ConfidenceThresholds | None = None,
    bins: int = 10,
    min_samples: int = 20,
    target_auto_hit_rate: float = 0.75,
    target_notify_hit_rate: float = 0.55,
) -> ThresholdCalibrationReport:
    thresholds = current_thresholds or ConfidenceThresholds()
    pairs = [
        (max(0.0, min(1.0, float(row.confidence))), _outcome_label(row))
        for row in rows
        if row.outcome.lower() in RESOLVED_OUTCOMES
    ]
    hits = sum(label for _, label in pairs)
    misses = len(pairs) - hits
    current_payload = {"auto": thresholds.auto, "notify": thresholds.notify}
    suggested = {
        "auto": _threshold_for_target(
            pairs,
            target_hit_rate=target_auto_hit_rate,
            min_samples=min_samples,
            fallback=thresholds.auto,
        ),
        "notify": _threshold_for_target(
            pairs,
            target_hit_rate=target_notify_hit_rate,
            min_samples=min_samples,
            fallback=thresholds.notify,
        ),
    }
    if suggested["notify"] > suggested["auto"]:
        suggested["notify"] = suggested["auto"]
    curve = isotonic_curve(pairs)
    expected_error = _expected_calibration_error(pairs, bins=bins)
    projected_error = projected_calibration_error(pairs, curve, bins=bins)
    return ThresholdCalibrationReport(
        signal_type=signal_type,
        category=category,
        samples=len(pairs),
        hits=hits,
        misses=misses,
        brier_score=_brier_score(pairs),
        expected_calibration_error=expected_error,
        projected_calibration_error=projected_error,
        calibration_error_improvement=(
            round(expected_error - projected_error, 6)
            if expected_error is not None and projected_error is not None
            else None
        ),
        bins=reliability_bins(pairs, bins=bins),
        isotonic_curve=curve,
        current_thresholds=current_payload,
        suggested_thresholds={key: round(value, 4) for key, value in suggested.items()},
        review_required=_meaningfully_changed(current_payload, suggested),
    )


async def enqueue_threshold_review(
    session: AsyncSession,
    report: ThresholdCalibrationReport,
) -> Any:
    proposed_change = {
        "key": "confidence_thresholds",
        "value": report.suggested_thresholds,
        "evidence": {
            "signal_type": report.signal_type,
            "category": report.category,
            "samples": report.samples,
            "hits": report.hits,
            "misses": report.misses,
            "brier_score": report.brier_score,
            "expected_calibration_error": report.expected_calibration_error,
        },
    }
    return await enqueue_review(
        session,
        source="calibration",
        target_table="alert_agent_config",
        target_key="confidence_thresholds",
        proposed_change=proposed_change,
        reason="Threshold calibration proposal from reliability diagram and isotonic fit.",
    )


def reliability_bins(
    pairs: list[tuple[float, int]],
    *,
    bins: int = 10,
) -> list[ReliabilityBin]:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for confidence, label in pairs:
        index = min(bins - 1, int(confidence * bins))
        buckets[index].append((confidence, label))

    results: list[ReliabilityBin] = []
    for index, bucket in enumerate(buckets):
        lower = index / bins
        upper = (index + 1) / bins
        if not bucket:
            results.append(
                ReliabilityBin(
                    lower=round(lower, 4),
                    upper=round(upper, 4),
                    samples=0,
                    avg_confidence=None,
                    hit_rate=None,
                    calibration_gap=None,
                )
            )
            continue
        avg_confidence = sum(confidence for confidence, _ in bucket) / len(bucket)
        hit_rate = sum(label for _, label in bucket) / len(bucket)
        results.append(
            ReliabilityBin(
                lower=round(lower, 4),
                upper=round(upper, 4),
                samples=len(bucket),
                avg_confidence=round(avg_confidence, 4),
                hit_rate=round(hit_rate, 4),
                calibration_gap=round(hit_rate - avg_confidence, 4),
            )
        )
    return results


def isotonic_curve(pairs: list[tuple[float, int]]) -> list[IsotonicPoint]:
    if not pairs:
        return []
    blocks: list[dict[str, float]] = []
    for confidence, label in sorted(pairs, key=lambda item: item[0]):
        blocks.append(
            {
                "confidence_sum": confidence,
                "label_sum": float(label),
                "samples": 1.0,
            }
        )
        while len(blocks) >= 2 and _block_mean(blocks[-2]) > _block_mean(blocks[-1]):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append(
                {
                    "confidence_sum": left["confidence_sum"] + right["confidence_sum"],
                    "label_sum": left["label_sum"] + right["label_sum"],
                    "samples": left["samples"] + right["samples"],
                }
            )
    return [
        IsotonicPoint(
            confidence=round(block["confidence_sum"] / block["samples"], 4),
            calibrated_probability=round(_block_mean(block), 4),
            samples=int(block["samples"]),
        )
        for block in blocks
    ]


def projected_calibration_error(
    pairs: list[tuple[float, int]],
    curve: list[IsotonicPoint],
    *,
    bins: int = 10,
) -> float | None:
    if not pairs or not curve:
        return None
    calibrated_pairs = [
        (isotonic_predict(confidence, curve), label)
        for confidence, label in pairs
    ]
    return _expected_calibration_error(calibrated_pairs, bins=bins)


def isotonic_predict(confidence: float, curve: list[IsotonicPoint]) -> float:
    if not curve:
        return confidence
    sorted_curve = sorted(curve, key=lambda item: item.confidence)
    for point in sorted_curve:
        if confidence <= point.confidence:
            return point.calibrated_probability
    return sorted_curve[-1].calibrated_probability


def _threshold_for_target(
    pairs: list[tuple[float, int]],
    *,
    target_hit_rate: float,
    min_samples: int,
    fallback: float,
) -> float:
    if len(pairs) < min_samples:
        return fallback
    for threshold in sorted({confidence for confidence, _ in pairs}):
        labels = [label for confidence, label in pairs if confidence >= threshold]
        if len(labels) < min_samples:
            continue
        if sum(labels) / len(labels) >= target_hit_rate:
            return threshold
    return fallback


def _outcome_label(row: SignalTrack) -> int:
    return 1 if row.outcome.lower() in HIT_OUTCOMES else 0


def _brier_score(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return round(sum((confidence - label) ** 2 for confidence, label in pairs) / len(pairs), 6)


def _expected_calibration_error(
    pairs: list[tuple[float, int]],
    *,
    bins: int,
) -> float | None:
    if not pairs:
        return None
    total = len(pairs)
    ece = 0.0
    for bucket in reliability_bins(pairs, bins=bins):
        if bucket.samples == 0 or bucket.calibration_gap is None:
            continue
        ece += (bucket.samples / total) * abs(bucket.calibration_gap)
    return round(ece, 6)


def _block_mean(block: dict[str, float]) -> float:
    return block["label_sum"] / block["samples"]


def _meaningfully_changed(current: dict[str, float], suggested: dict[str, float]) -> bool:
    return any(abs(float(current[key]) - float(suggested[key])) >= 0.02 for key in current)
