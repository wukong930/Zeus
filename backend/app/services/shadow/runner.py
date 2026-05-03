import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.events import ZeusEvent
from app.models.shadow_runs import ShadowRun
from app.models.shadow_signals import ShadowSignal
from app.services.alert_agent.config import ConfidenceThresholds
from app.services.alert_agent.dedup import combined_score, primary_symbol
from app.services.calibration.tracker import get_calibration_weight
from app.services.pipeline.handlers import (
    DEFAULT_ACCOUNT_NET_VALUE,
    DEFAULT_MARGIN_REQUIRED,
    NEWS_EVENT_SIGNAL_TYPES,
    _spread_info_from_payload,
    jsonable,
    open_positions_for_scoring,
    recommendation_legs_from_signal,
    trigger_context_from_payload,
    trigger_context_payloads,
)
from app.services.scoring.engine import apply_calibration_weight, score_recommendation
from app.services.signals.detector import SignalDetector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowRunResult:
    scanned: int
    written: int
    would_emit: int


@dataclass(frozen=True)
class ShadowThresholdConfig:
    min_confidence: float
    min_combined_score: float


async def create_shadow_run(
    session: AsyncSession,
    *,
    name: str,
    algorithm_version: str,
    config_diff: dict[str, Any] | None = None,
    created_by: str | None = None,
    notes: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> ShadowRun:
    row = ShadowRun(
        name=name,
        algorithm_version=algorithm_version,
        config_diff=config_diff or {},
        status="active",
        started_at=started_at or datetime.now(timezone.utc),
        ended_at=ended_at,
        created_by=created_by,
        notes=notes,
    )
    session.add(row)
    await session.flush()
    return row


async def stop_shadow_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    ended_at: datetime | None = None,
) -> ShadowRun | None:
    row = await session.get(ShadowRun, run_id)
    if row is None:
        return None
    row.status = "completed"
    row.ended_at = ended_at or datetime.now(timezone.utc)
    await session.flush()
    return row


async def active_shadow_runs(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
) -> list[ShadowRun]:
    effective_at = as_of or datetime.now(timezone.utc)
    return list(
        (
            await session.scalars(
                select(ShadowRun)
                .where(
                    ShadowRun.status == "active",
                    ShadowRun.started_at <= effective_at,
                    or_(ShadowRun.ended_at.is_(None), ShadowRun.ended_at > effective_at),
                )
                .order_by(ShadowRun.started_at.asc())
            )
        ).all()
    )


async def handle_shadow_event(event: ZeusEvent) -> None:
    try:
        async with AsyncSessionLocal() as session:
            runs = await active_shadow_runs(session, as_of=event.timestamp)
            for run in runs:
                await run_shadow_for_event(session, run, event)
            await session.commit()
    except Exception:
        logger.exception("Shadow event processing failed for %s", event.channel)


async def run_shadow_for_event(
    session: AsyncSession,
    run: ShadowRun,
    event: ZeusEvent,
    *,
    detector: SignalDetector | None = None,
) -> ShadowRunResult:
    candidates = await _signal_candidates_from_event(event, detector=detector)
    written = 0
    would_emit = 0
    for signal, context, score_payload in candidates:
        score = score_payload or await _score_signal(session, run, signal=signal, context=context)
        row = await record_shadow_signal(
            session,
            run=run,
            event=event,
            signal=signal,
            context=context,
            score=score,
        )
        written += 1
        would_emit += int(row.would_emit)
    return ShadowRunResult(scanned=len(candidates), written=written, would_emit=would_emit)


async def record_shadow_signal(
    session: AsyncSession,
    *,
    run: ShadowRun,
    event: ZeusEvent,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any],
) -> ShadowSignal:
    thresholds = shadow_threshold_config(run.config_diff)
    confidence = float(signal.get("confidence") or 0)
    score_value = combined_score(score)
    would_emit = confidence >= thresholds.min_confidence and score_value >= thresholds.min_combined_score
    row = ShadowSignal(
        shadow_run_id=run.id,
        source_event_type=event.channel,
        source_event_id=event.id,
        correlation_id=event.correlation_id,
        signal_type=str(signal.get("signal_type") or "unknown"),
        category=str(context.get("category") or signal.get("category") or "unknown"),
        symbol=primary_symbol(signal),
        would_emit=would_emit,
        confidence=confidence,
        score=score_value,
        threshold=thresholds.min_confidence,
        production_signal_track_id=_optional_uuid(score.get("signal_track_id")),
        production_alert_id=_optional_uuid(score.get("alert_id")),
        reason=_shadow_reason(confidence, score_value, thresholds),
        signal_payload=jsonable(signal),
        context_payload=jsonable(context),
        score_payload=jsonable(score),
    )
    session.add(row)
    await session.flush()
    return row


def shadow_threshold_config(config_diff: dict[str, Any] | None) -> ShadowThresholdConfig:
    config = config_diff or {}
    thresholds = config.get("confidence_thresholds")
    if not isinstance(thresholds, dict):
        thresholds = {}
    defaults = ConfidenceThresholds()
    min_confidence = float(
        config.get(
            "min_confidence",
            thresholds.get("notify", defaults.notify),
        )
    )
    min_combined_score = float(config.get("min_combined_score", 60))
    return ShadowThresholdConfig(
        min_confidence=max(0.0, min(1.0, min_confidence)),
        min_combined_score=max(0.0, min(100.0, min_combined_score)),
    )


async def _signal_candidates_from_event(
    event: ZeusEvent,
    *,
    detector: SignalDetector | None,
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    payload = event.payload
    if event.channel in {"signal.detected", "signal.scored"}:
        signal = payload.get("signal")
        if not isinstance(signal, dict):
            return []
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        score = payload.get("score") if isinstance(payload.get("score"), dict) else None
        if score is not None:
            score = dict(score)
            for key in ("signal_track_id", "alert_id"):
                if payload.get(key) is not None:
                    score[key] = payload[key]
        return [(jsonable(signal), jsonable(context), jsonable(score) if score is not None else None)]

    contexts_payload = trigger_context_payloads(event)
    if event.channel == "news.event" and not contexts_payload:
        news_event = payload.get("news_event")
        if isinstance(news_event, dict):
            contexts_payload = [
                {
                    "symbol1": symbol,
                    "category": "unknown",
                    "timestamp": news_event.get("published_at") or event.timestamp.isoformat(),
                    "regime": "news",
                    "news_events": [news_event],
                }
                for symbol in news_event.get("affected_symbols", [])
            ]
    if event.channel not in {"market.update", "news.event"}:
        return []

    signal_detector = detector or SignalDetector()
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]] = []
    signal_types = NEWS_EVENT_SIGNAL_TYPES if event.channel == "news.event" else None
    for raw_context in contexts_payload:
        context = trigger_context_from_payload(raw_context)
        context_payload = jsonable(context)
        if raw_context.get("regime") is not None:
            context_payload["regime"] = raw_context["regime"]
        if raw_context.get("regime_at_emission") is not None:
            context_payload["regime_at_emission"] = raw_context["regime_at_emission"]
        for result in await signal_detector.detect(context, signal_types=signal_types):
            candidates.append((jsonable(result), context_payload, None))
    return candidates


async def _score_signal(
    session: AsyncSession,
    run: ShadowRun,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    category = str(context.get("category") or signal.get("category") or "unknown")
    regime = str(context.get("regime") or context.get("regime_at_emission") or "unknown")
    calibration_weight = await get_calibration_weight(
        session,
        signal_type=str(signal.get("signal_type") or "unknown"),
        category=category,
        regime=regime,
    )
    calibration_weight = _override_calibration_weight(run.config_diff, signal, calibration_weight)
    base_score = score_recommendation(
        spread_info=_spread_info_from_payload(signal.get("spread_info")),
        confidence=float(signal.get("confidence") or 0),
        legs=recommendation_legs_from_signal(signal),
        open_positions=await open_positions_for_scoring(session, {"open_positions": []}),
        margin_required=float(run.config_diff.get("margin_required", DEFAULT_MARGIN_REQUIRED)),
        account_net_value=float(
            run.config_diff.get("account_net_value", DEFAULT_ACCOUNT_NET_VALUE)
        ),
    )
    score = apply_calibration_weight(base_score, calibration_weight)
    return {
        "priority": score.priority,
        "portfolio_fit": score.portfolio_fit,
        "margin_efficiency": score.margin_efficiency,
        "combined": score.combined,
        "base_score": jsonable(base_score),
        "calibration_weight": calibration_weight,
    }


def _override_calibration_weight(
    config_diff: dict[str, Any],
    signal: dict[str, Any],
    default_weight: float,
) -> float:
    overrides = config_diff.get("calibration_weight_overrides")
    if not isinstance(overrides, dict):
        return default_weight
    key = str(signal.get("signal_type") or "unknown")
    if key not in overrides:
        return default_weight
    return float(overrides[key])


def _shadow_reason(
    confidence: float,
    score: float,
    thresholds: ShadowThresholdConfig,
) -> str:
    if confidence < thresholds.min_confidence:
        return "below_confidence_threshold"
    if score < thresholds.min_combined_score:
        return "below_score_threshold"
    return "would_emit"


def _optional_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
