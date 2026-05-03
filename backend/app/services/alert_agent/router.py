from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.calibration import SignalCalibration
from app.services.alert_agent.classifier import classify_alert
from app.services.alert_agent.config import ConfidenceThresholds, load_confidence_thresholds
from app.services.alert_agent.narrative import generate_narrative, generate_one_liner
from app.services.learning.user_feedback import feedback_hint_for_signal

CONFIRM_DEADLINE_HOURS = 2


@dataclass(frozen=True)
class AlertRouteDecision:
    route: str
    confidence_tier: str
    classification: str
    human_action_required: bool
    human_action_deadline: datetime | None
    llm_involved: bool
    narrative: str
    one_liner: str
    reasons: list[str]


async def route_alert(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None,
    as_of: datetime | None = None,
) -> AlertRouteDecision:
    effective_at = as_of or datetime.now(timezone.utc)
    classification = classify_alert(signal, score)
    confidence = float(signal.get("confidence") or 0)
    thresholds = await load_confidence_thresholds(session)
    confidence_tier = confidence_tier_for(confidence, thresholds)
    reasons: list[str] = [f"confidence:{confidence_tier}", f"classification:{classification}"]

    conflict = has_direction_conflict(signal, context)
    if conflict:
        reasons.append("direction_conflict")

    signal_types = signal_type_set(signal, context)
    fuzzy_confidence = 0.40 <= confidence <= 0.65 and len(signal_types) >= 3
    if fuzzy_confidence:
        reasons.append("fuzzy_confidence")

    no_history = await lacks_history(session, signal=signal, context=context)
    if no_history:
        reasons.append("no_calibration_history")

    cross_sector = crosses_three_sectors(signal)
    if cross_sector:
        reasons.append("cross_sector_chain")

    feedback_hint = await feedback_hint_for_signal(
        session,
        signal_type=str(signal.get("signal_type") or "unknown"),
    )
    if feedback_hint is not None:
        reasons.append("feedback_caution")

    llm_candidate = conflict or fuzzy_confidence or no_history or cross_sector
    llm_involved = False
    arbitration_narrative: str | None = None
    if llm_candidate:
        from app.services.alert_agent.llm_arbiter import arbitrate_signal

        arbitration = await arbitrate_signal(
            session,
            signal=signal,
            context=context,
            score=score,
        )
        classification = arbitration.classification
        llm_involved = not arbitration.fallback_used
        arbitration_narrative = arbitration.narrative

    route = route_for(confidence_tier, conflict=conflict, llm_candidate=llm_candidate)
    human_required = route in {"confirm", "arbitrate"}
    deadline = effective_at + timedelta(hours=CONFIRM_DEADLINE_HOURS) if human_required else None

    narrative = arbitration_narrative or generate_narrative(signal, classification)
    if feedback_hint is not None:
        narrative = f"{narrative} {feedback_hint.hint}"

    return AlertRouteDecision(
        route=route,
        confidence_tier=confidence_tier,
        classification=classification,
        human_action_required=human_required,
        human_action_deadline=deadline,
        llm_involved=llm_involved,
        narrative=narrative,
        one_liner=generate_one_liner(signal, classification),
        reasons=reasons,
    )


def confidence_tier_for(
    confidence: float,
    thresholds: ConfidenceThresholds | None = None,
) -> str:
    active_thresholds = thresholds or ConfidenceThresholds()
    if confidence > active_thresholds.auto:
        return "auto"
    if confidence >= active_thresholds.notify:
        return "notify"
    return "confirm"


def route_for(confidence_tier: str, *, conflict: bool, llm_candidate: bool) -> str:
    if conflict:
        return "arbitrate"
    if confidence_tier == "confirm":
        return "confirm"
    if llm_candidate:
        return "arbitrate"
    return confidence_tier


def signal_type_set(signal: dict[str, Any], context: dict[str, Any]) -> set[str]:
    raw = context.get("signal_types") or context.get("signal_type_set")
    if isinstance(raw, (list, tuple, set)):
        values = {str(item) for item in raw if str(item)}
        if values:
            return values
    return {str(signal.get("signal_type") or "unknown")}


def has_direction_conflict(signal: dict[str, Any], context: dict[str, Any]) -> bool:
    if context.get("direction_conflict") is True:
        return True
    text = " ".join(
        str(item).lower()
        for item in (
            signal.get("title", ""),
            signal.get("summary", ""),
            *signal.get("risk_items", []),
        )
    )
    bullish = any(marker in text for marker in ("bullish", "long", "上行", "偏多"))
    bearish = any(marker in text for marker in ("bearish", "short", "下行", "偏空"))
    return bullish and bearish


async def lacks_history(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    if session is None:
        return False
    try:
        row = (
            await session.scalars(
                select(SignalCalibration)
                .where(
                    SignalCalibration.signal_type == str(signal.get("signal_type") or "unknown"),
                    SignalCalibration.category
                    == str(context.get("category") or signal.get("category") or "unknown"),
                    SignalCalibration.regime
                    == str(context.get("regime") or context.get("regime_at_emission") or "unknown"),
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return False
    return row is None


def crosses_three_sectors(signal: dict[str, Any]) -> bool:
    sectors = {symbol_sector(str(asset)) for asset in signal.get("related_assets", [])}
    sectors.discard("unknown")
    return len(sectors) >= 3


def symbol_sector(symbol: str) -> str:
    root = "".join(char for char in symbol.upper() if char.isalpha())
    if root in {"RB", "HC", "I", "J", "JM", "SF", "SM"}:
        return "ferrous"
    if root in {"RU", "NR", "BR"}:
        return "rubber"
    if root in {"SC", "FU", "TA", "EG", "MA", "PP", "L", "V"}:
        return "energy"
    if root in {"CU", "AL", "ZN", "NI", "SN", "PB"}:
        return "nonferrous"
    if root in {"M", "Y", "P", "C", "A", "CF", "SR"}:
        return "agriculture"
    return "unknown"
