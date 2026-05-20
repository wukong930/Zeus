import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ZeusEvent, publish
from app.models.alert import Alert
from app.models.position import Position
from app.models.recommendation import Recommendation
from app.models.signal import SignalTrack
from app.services.adversarial.engine import (
    attach_signal_track_to_adversarial_result,
    evaluate_adversarial_signal,
)
from app.services.alert_agent.dedup import (
    check_alert_dedup,
    primary_symbol,
    record_alert_emitted,
    signal_direction,
)
from app.services.alert_agent.router import route_alert
from app.services.calibration.tracker import get_calibration_weight, track_signal_emission
from app.services.scoring.engine import CombinedScore, apply_calibration_weight, score_recommendation
from app.services.scoring.portfolio_fit import PositionGroup, RecommendationLeg
from app.services.risk.stress import symbol_prefix
from app.services.scenarios import (
    ScenarioRequest,
    run_scenario_simulation,
    run_scenario_simulation_with_llm_narrative,
)
from app.services.signals.detector import SignalDetector
from app.services.signals.types import (
    CostSnapshotPoint,
    IndustryPoint,
    MarketBar,
    NewsEventPoint,
    SpreadInfo,
    SpreadStatistics,
    TriggerContext,
)
from app.services.translation import apply_alert_translation

EventPublisher = Callable[..., Awaitable[ZeusEvent]]

DEFAULT_ACCOUNT_NET_VALUE = 1_000_000.0
DEFAULT_MARGIN_REQUIRED = 100_000.0
NEWS_EVENT_SIGNAL_TYPES = {"news_event", "rubber_supply_shock"}
TRADE_PLAN_DIRECTIONAL_ACTION = "open_directional"
TRADE_PLAN_ACTIONS = {"open_spread", TRADE_PLAN_DIRECTIONAL_ACTION}
TRADE_PLAN_DIRECTIONAL_SIGNAL_TYPES = {
    "capacity_contraction",
    "event_driven",
    "inventory_shock",
    "marginal_capacity_squeeze",
    "median_pressure",
    "momentum",
    "news_event",
    "price_gap",
    "restart_expectation",
    "rubber_supply_shock",
}
TRADE_PLAN_CONTEXT_SIGNAL_TYPES = {
    "inventory_shock",
    "regime_shift",
}
TRADE_PLAN_CONTEXT_SKIP_REASONS = {
    "missing_direction",
    "score_below_gate",
    "unsupported_action",
}
TRADE_PLAN_MIN_COMBINED_SCORE = 80.0
TRADE_PLAN_MIN_CONFIDENCE = 0.70
TRADE_PLAN_MIN_DIRECTIONAL_SCORE = 62.0
TRADE_PLAN_MIN_DIRECTIONAL_CONFIDENCE = 0.82
TRADE_PLAN_DEFAULT_HOLDING_DAYS = 20
TRADE_PLAN_EXPIRES_AFTER = timedelta(days=1)
TRADE_PLAN_OPEN_STATUSES = {"pending", "pending_review"}
TRADE_PLAN_MAX_RISK_ITEMS = 20

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradePlanCandidateEvaluation:
    recommendation: Recommendation | None
    skip_reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.recommendation is not None


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def _parse_datetime(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def context_triggered_at(context: dict[str, Any]) -> datetime:
    return _parse_datetime(context.get("freshness_timestamp") or context.get("timestamp"))


def trigger_context_from_payload(payload: dict[str, Any]) -> TriggerContext:
    spread_stats = payload.get("spread_stats")
    return TriggerContext(
        symbol1=str(payload["symbol1"]),
        symbol2=payload.get("symbol2"),
        category=str(payload["category"]),
        timestamp=_parse_datetime(payload.get("timestamp")),
        market_data=[
            MarketBar(
                timestamp=_parse_datetime(row.get("timestamp")),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                open_interest=(
                    float(row["open_interest"]) if row.get("open_interest") is not None else None
                ),
            )
            for row in payload.get("market_data", [])
        ],
        inventory=[
            IndustryPoint(
                value=float(row["value"]),
                timestamp=_parse_datetime(row.get("timestamp")),
            )
            for row in payload.get("inventory", [])
        ],
        cost_snapshots=[
            CostSnapshotPoint(
                symbol=str(row.get("symbol") or payload["symbol1"]).upper(),
                timestamp=_parse_datetime(
                    row.get("timestamp")
                    or row.get("snapshot_date")
                    or row.get("created_at")
                ),
                current_price=(
                    float(row["current_price"]) if row.get("current_price") is not None else None
                ),
                total_unit_cost=float(row["total_unit_cost"]),
                breakeven_p25=float(row["breakeven_p25"]),
                breakeven_p50=float(row["breakeven_p50"]),
                breakeven_p75=float(row["breakeven_p75"]),
                breakeven_p90=float(row["breakeven_p90"]),
                profit_margin=(
                    float(row["profit_margin"]) if row.get("profit_margin") is not None else None
                ),
                uncertainty_pct=float(row.get("uncertainty_pct", 0.05)),
            )
            for row in payload.get("cost_snapshots", [])
        ],
        news_events=[
            NewsEventPoint(
                id=str(row.get("id") or ""),
                source=str(row.get("source") or "unknown"),
                title=str(row.get("title") or "Untitled event"),
                summary=str(row.get("summary") or row.get("title") or ""),
                published_at=_parse_datetime(row.get("published_at") or row.get("timestamp")),
                event_type=str(row.get("event_type") or "breaking"),
                affected_symbols=[
                    str(symbol).upper()
                    for symbol in row.get("affected_symbols", [])
                    if str(symbol).strip()
                ],
                direction=str(row.get("direction") or "unclear"),
                severity=int(row.get("severity") or 1),
                time_horizon=str(row.get("time_horizon") or "short"),
                confidence=float(row.get("confidence", row.get("llm_confidence", 0))),
                source_count=int(row.get("source_count") or 1),
                verification_status=str(row.get("verification_status") or "single_source"),
                requires_manual_confirmation=bool(row.get("requires_manual_confirmation", False)),
                raw_url=row.get("raw_url"),
                title_original=row.get("title_original"),
                summary_original=row.get("summary_original"),
                title_zh=row.get("title_zh"),
                summary_zh=row.get("summary_zh"),
                source_language=str(row.get("source_language") or "unknown"),
                translation_status=str(row.get("translation_status") or "pending"),
            )
            for row in payload.get("news_events", [])
        ],
        spread_stats=(
            SpreadStatistics(
                adf_p_value=float(spread_stats["adf_p_value"]),
                half_life=float(spread_stats["half_life"]),
                spread_mean=float(spread_stats["spread_mean"]),
                spread_std_dev=float(spread_stats["spread_std_dev"]),
                current_z_score=float(spread_stats["current_z_score"]),
                raw_spread_mean=(
                    float(spread_stats["raw_spread_mean"])
                    if spread_stats.get("raw_spread_mean") is not None
                    else None
                ),
                raw_spread_std_dev=(
                    float(spread_stats["raw_spread_std_dev"])
                    if spread_stats.get("raw_spread_std_dev") is not None
                    else None
                ),
            )
            if spread_stats is not None
            else None
        ),
        in_roll_window=bool(payload.get("in_roll_window", False)),
    )


def trigger_context_payloads(event: ZeusEvent) -> list[dict[str, Any]]:
    payload = event.payload
    if "contexts" in payload:
        return list(payload["contexts"])
    if "trigger_contexts" in payload:
        return list(payload["trigger_contexts"])
    if "context" in payload:
        return [payload["context"]]
    return []


def parse_trigger_contexts(
    raw_contexts: list[dict[str, Any]],
    *,
    channel: str,
) -> list[tuple[dict[str, Any], TriggerContext]]:
    parsed: list[tuple[dict[str, Any], TriggerContext]] = []
    for index, raw_context in enumerate(raw_contexts):
        if not isinstance(raw_context, dict):
            logger.warning("Skipping non-object trigger context %s for %s", index, channel)
            continue
        try:
            parsed.append((raw_context, trigger_context_from_payload(raw_context)))
        except Exception:
            logger.warning("Skipping malformed trigger context %s for %s", index, channel, exc_info=True)
    return parsed


async def handle_news_event(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    detector: SignalDetector | None = None,
    publisher: EventPublisher = publish,
) -> list[ZeusEvent]:
    contexts_payload = trigger_context_payloads(event)
    if not contexts_payload:
        news_event = event.payload.get("news_event")
        if not isinstance(news_event, dict):
            return []
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

    signal_detector = detector or SignalDetector()
    published: list[ZeusEvent] = []
    for raw_context, context in parse_trigger_contexts(contexts_payload, channel=event.channel):
        results = await signal_detector.detect(context, signal_types=NEWS_EVENT_SIGNAL_TYPES)
        context_payload = jsonable(context)
        if raw_context.get("regime") is not None:
            context_payload["regime"] = raw_context["regime"]
        if raw_context.get("freshness_timestamp") is not None:
            context_payload["freshness_timestamp"] = raw_context["freshness_timestamp"]
        for result in results:
            published.append(
                await publisher(
                    "signal.detected",
                    {
                        "signal": jsonable(result),
                        "context": context_payload,
                    },
                    source="news-event-evaluator",
                    correlation_id=event.correlation_id,
                    session=session,
                )
            )
    return published


async def handle_market_update(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    detector: SignalDetector | None = None,
    publisher: EventPublisher = publish,
) -> list[ZeusEvent]:
    raw_contexts = trigger_context_payloads(event)
    contexts = parse_trigger_contexts(raw_contexts, channel=event.channel)
    if not contexts:
        return []

    signal_detector = detector or SignalDetector()
    published: list[ZeusEvent] = []
    for raw_context, context in contexts:
        results = await signal_detector.detect(context)
        context_payload = jsonable(context)
        if raw_context.get("regime") is not None:
            context_payload["regime"] = raw_context["regime"]
        if raw_context.get("regime_at_emission") is not None:
            context_payload["regime_at_emission"] = raw_context["regime_at_emission"]
        if raw_context.get("freshness_timestamp") is not None:
            context_payload["freshness_timestamp"] = raw_context["freshness_timestamp"]
        for result in results:
            published.append(
                await publisher(
                    "signal.detected",
                    {
                        "signal": jsonable(result),
                        "context": context_payload,
                    },
                    source="signal-detector",
                    correlation_id=event.correlation_id,
                    session=session,
                )
            )
    return published


async def handle_signal_detected(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    publisher: EventPublisher = publish,
) -> ZeusEvent | None:
    signal = event.payload.get("signal")
    if not isinstance(signal, dict):
        return None

    context = event.payload.get("context", {})
    category = str(context.get("category") or signal.get("category") or "unknown")
    regime = context.get("regime") or context.get("regime_at_emission") or "unknown"
    adversarial_decision = await evaluate_adversarial_signal(
        session,
        signal=signal,
        context=context,
        correlation_id=event.correlation_id,
    )
    if adversarial_decision.suppressed:
        return await publisher(
            "signal.suppressed",
            {
                "signal": signal,
                "context": context,
                "adversarial_result": adversarial_decision.to_payload(),
            },
            source="adversarial-engine",
            correlation_id=event.correlation_id,
            session=session,
        )

    signal = adversarial_decision.adjusted_signal
    spread_info = _spread_info_from_payload(signal.get("spread_info"))
    legs = recommendation_legs_from_signal(signal)
    open_positions = await open_positions_for_scoring(session, event.payload)
    margin_required = float(event.payload.get("margin_required", DEFAULT_MARGIN_REQUIRED))
    account_net_value = float(event.payload.get("account_net_value", DEFAULT_ACCOUNT_NET_VALUE))
    calibration_weight = await get_calibration_weight(
        session,
        signal_type=str(signal["signal_type"]),
        category=category,
        regime=str(regime),
    )
    base_score = score_recommendation(
        spread_info=spread_info,
        confidence=float(signal.get("confidence", 0)),
        legs=legs,
        open_positions=open_positions,
        margin_required=margin_required,
        account_net_value=account_net_value,
    )
    conflicts = position_conflict_warnings(legs, open_positions)
    if conflicts:
        signal = {
            **signal,
            "risk_items": list(signal.get("risk_items", [])) + conflicts,
        }
        base_score = boost_priority_for_position_signal(base_score, boost=10)
    score = apply_calibration_weight(base_score, calibration_weight)
    signal_track = await track_signal_emission(
        session,
        signal=signal,
        category=category,
        regime=str(regime),
        calibration_weight=calibration_weight,
        adversarial_passed=adversarial_decision.passed,
    )
    if signal_track is not None:
        await attach_signal_track_to_adversarial_result(
            session,
            result_id=adversarial_decision.result_id,
            signal_track_id=signal_track.id,
        )

    return await publisher(
        "signal.scored",
        {
            "signal": signal,
            "context": context,
            "score": jsonable(score),
            "base_score": jsonable(base_score),
            "calibration_weight": calibration_weight,
            "adversarial_result": adversarial_decision.to_payload(),
            "signal_track_id": str(signal_track.id) if signal_track is not None else None,
            "legs": jsonable(legs),
            "margin_required": margin_required,
            "account_net_value": account_net_value,
            "recommended_action": recommended_action(signal),
        },
        source="scoring-engine",
        correlation_id=event.correlation_id,
        session=session,
    )


async def handle_signal_scored(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    publisher: EventPublisher = publish,
) -> ZeusEvent | None:
    if session is None:
        return None

    signal = event.payload.get("signal")
    if not isinstance(signal, dict):
        return None

    alert_id = uuid4()
    score = event.payload.get("score", {})
    context = event.payload.get("context", {})
    triggered_at = context_triggered_at(context) if isinstance(context, dict) else datetime.now(timezone.utc)
    agent_decision = await route_alert(
        session,
        signal=signal,
        context=context,
        score=score,
    )
    dedup_decision = await check_alert_dedup(
        session,
        signal=signal,
        context=context,
        score=score,
        signal_combination_hash=event.payload.get("adversarial_result", {}).get(
            "signal_combination_hash"
        ),
    )
    status = (
        "suppressed"
        if dedup_decision.suppressed
        else "pending"
        if agent_decision.human_action_required
        else "active"
    )
    translated_alert = apply_alert_translation(
        {
            "title": str(signal["title"]),
            "summary": agent_decision.narrative,
        }
    )
    alert = Alert(
        id=alert_id,
        title=str(translated_alert.get("title_zh") or translated_alert["title"]),
        summary=str(translated_alert.get("summary_zh") or translated_alert["summary"]),
        title_original=translated_alert.get("title_original"),
        summary_original=translated_alert.get("summary_original"),
        title_zh=translated_alert.get("title_zh"),
        summary_zh=translated_alert.get("summary_zh"),
        source_language=str(translated_alert.get("source_language") or "unknown"),
        translation_status=str(translated_alert.get("translation_status") or "pending"),
        translation_model=translated_alert.get("translation_model"),
        translation_prompt_version=translated_alert.get("translation_prompt_version"),
        translation_glossary_version=translated_alert.get("translation_glossary_version"),
        translated_at=translated_alert.get("translated_at"),
        severity=str(signal["severity"]),
        category=str(context.get("category") or "unknown"),
        type=str(signal["signal_type"]),
        status=status,
        triggered_at=triggered_at,
        expires_at=triggered_at + timedelta(days=1),
        confidence=float(signal.get("confidence", 0)),
        adversarial_passed=bool(event.payload.get("adversarial_result", {}).get("passed", False)),
        llm_involved=agent_decision.llm_involved,
        confidence_tier=agent_decision.confidence_tier,
        human_action_required=agent_decision.human_action_required,
        human_action_deadline=agent_decision.human_action_deadline,
        dedup_suppressed=dedup_decision.suppressed,
        related_assets=list(signal.get("related_assets", [])),
        spread_info=signal.get("spread_info"),
        trigger_chain=list(signal.get("trigger_chain", [])),
        risk_items=list(signal.get("risk_items", [])),
        manual_check_items=list(signal.get("manual_check_items", [])),
        one_liner=agent_decision.one_liner,
    )
    session.add(alert)
    await session.flush()
    await attach_alert_to_signal_track(session, event.payload.get("signal_track_id"), alert)
    if dedup_decision.suppressed:
        return await publisher(
            "alert.suppressed",
            {
                "alert_id": str(alert.id),
                "signal_type": alert.type,
                "severity": alert.severity,
                "category": alert.category,
                "dedup_reason": dedup_decision.reason,
                "confidence_tier": alert.confidence_tier,
                "related_assets": alert.related_assets,
            },
            source="alert-agent",
            correlation_id=event.correlation_id,
            session=session,
        )

    scenario_request = scenario_request_from_alert(signal, context, score)
    if agent_decision.route == "arbitrate" and scenario_request is not None:
        await publisher(
            "scenario.requested",
            {
                "request": scenario_request,
                "use_llm_narrative": True,
                "trigger": {
                    "alert_id": str(alert.id),
                    "route": agent_decision.route,
                    "confidence_tier": agent_decision.confidence_tier,
                    "reasons": agent_decision.reasons,
                    "signal_type": alert.type,
                },
            },
            source="alert-agent",
            correlation_id=event.correlation_id,
            session=session,
        )

    await record_alert_emitted(
        session,
        signal=signal,
        signal_combination_hash=event.payload.get("adversarial_result", {}).get(
            "signal_combination_hash"
        ),
        emitted_at=triggered_at,
        score=score,
    )
    trade_plan_event_payload = {
        **event.payload,
        "alert_route": {
            "route": agent_decision.route,
            "confidence_tier": agent_decision.confidence_tier,
            "classification": agent_decision.classification,
            "human_action_required": agent_decision.human_action_required,
            "llm_involved": agent_decision.llm_involved,
            "reasons": agent_decision.reasons,
        },
    }
    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal=signal,
        context=context,
        score=score,
        event_payload=trade_plan_event_payload,
        triggered_at=triggered_at,
    )
    recommendation = evaluation.recommendation
    if recommendation is not None:
        existing_plan = await open_trade_plan_for_candidate(
            session,
            recommendation,
            as_of=datetime.now(timezone.utc),
        )
        if existing_plan is not None:
            merge_trade_plan_evidence(existing_plan, recommendation, alert=alert)
            await session.flush()
            alert.related_recommendation_id = existing_plan.id
            await publisher(
                "recommendation.linked",
                {
                    "recommendation_id": str(existing_plan.id),
                    "alert_id": str(alert.id),
                    "recommended_action": existing_plan.recommended_action,
                    "source_signal_type": alert.type,
                    "source_alert_severity": alert.severity,
                },
                source="trade-plan-generator",
                correlation_id=event.correlation_id,
                session=session,
            )
        else:
            session.add(recommendation)
            await session.flush()
            alert.related_recommendation_id = recommendation.id
            await publisher(
                "recommendation.created",
                {
                    "recommendation_id": str(recommendation.id),
                    "alert_id": str(alert.id),
                    "recommended_action": recommendation.recommended_action,
                    "priority_score": recommendation.priority_score,
                    "portfolio_fit_score": recommendation.portfolio_fit_score,
                    "margin_efficiency_score": recommendation.margin_efficiency_score,
                    "source_signal_type": alert.type,
                    "source_alert_severity": alert.severity,
                },
                source="trade-plan-generator",
                correlation_id=event.correlation_id,
                session=session,
            )
    elif evaluation.skip_reason in TRADE_PLAN_CONTEXT_SKIP_REASONS:
        context_plan = await open_trade_plan_for_context_signal(
            session,
            signal,
            skip_reason=evaluation.skip_reason,
            as_of=datetime.now(timezone.utc),
        )
        if context_plan is not None:
            attach_trade_plan_context_evidence(
                context_plan,
                alert=alert,
                signal=signal,
                skip_reason=evaluation.skip_reason,
            )
            await session.flush()
            alert.related_recommendation_id = context_plan.id
            await publisher(
                "recommendation.context_linked",
                {
                    "recommendation_id": str(context_plan.id),
                    "alert_id": str(alert.id),
                    "recommended_action": context_plan.recommended_action,
                    "source_signal_type": alert.type,
                    "source_alert_severity": alert.severity,
                    "skip_reason": evaluation.skip_reason,
                },
                source="trade-plan-generator",
                correlation_id=event.correlation_id,
                session=session,
            )

    return await publisher(
        "alert.created",
        {
            "alert_id": str(alert.id),
            "recommendation_id": (
                str(alert.related_recommendation_id)
                if alert.related_recommendation_id is not None
                else None
            ),
            "signal_type": alert.type,
            "severity": alert.severity,
            "category": alert.category,
            "score": score,
            "adversarial_passed": alert.adversarial_passed,
            "confidence_tier": alert.confidence_tier,
            "human_action_required": alert.human_action_required,
            "llm_involved": alert.llm_involved,
            "related_assets": alert.related_assets,
        },
        source="alert-agent",
        correlation_id=event.correlation_id,
        session=session,
    )


async def handle_scenario_requested(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    publisher: EventPublisher = publish,
) -> ZeusEvent | None:
    request_payload = event.payload.get("request", event.payload)
    if not isinstance(request_payload, dict):
        return None

    request = ScenarioRequest(
        target_symbol=str(request_payload["target_symbol"]),
        shocks={
            str(symbol): float(shock)
            for symbol, shock in dict(request_payload.get("shocks") or {}).items()
        },
        base_price=(
            float(request_payload["base_price"])
            if request_payload.get("base_price") is not None
            else None
        ),
        days=int(request_payload.get("days", 20)),
        simulations=int(request_payload.get("simulations", 1000)),
        volatility_pct=(
            float(request_payload["volatility_pct"])
            if request_payload.get("volatility_pct") is not None
            else None
        ),
        drift_pct=float(request_payload.get("drift_pct", 0.0)),
        seed=int(request_payload.get("seed", 7)),
        max_depth=int(request_payload.get("max_depth", 3)),
    )
    runtime_payload = event.payload.get("runtime")
    runtime = scenario_runtime_metadata(runtime_payload if isinstance(runtime_payload, dict) else {})
    if event.payload.get("use_llm_narrative", False):
        report = await run_scenario_simulation_with_llm_narrative(
            request,
            session=session,
            **runtime,
        )
    else:
        report = run_scenario_simulation(request, **runtime)
    return await publisher(
        "scenario.completed",
        {"report": report.to_dict()},
        source="scenario-simulator",
        correlation_id=event.correlation_id,
        session=session,
    )


def scenario_request_from_alert(
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None,
) -> dict[str, Any] | None:
    target_symbol = _target_symbol_from_signal(signal, context)
    if target_symbol is None:
        return None

    shock_size = _shock_size_for_signal(signal, score)
    direction = signal_direction(signal)
    sign = -1 if direction == "bearish" else 1
    return {
        "target_symbol": target_symbol,
        "shocks": {target_symbol: round(sign * shock_size, 4)},
        "base_price": _latest_context_price(context),
        "days": 20,
        "simulations": 1000,
        "seed": 17,
        "max_depth": 3,
    }


def scenario_runtime_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("base_price_source")
    sections = payload.get("unavailable_sections")
    return {
        "base_price_source": source if isinstance(source, str) else None,
        "unavailable_sections": tuple(
            str(item)
            for item in (sections if isinstance(sections, list) else [])
            if item
        ),
    }


def _target_symbol_from_signal(signal: dict[str, Any], context: dict[str, Any]) -> str | None:
    candidates = [
        primary_symbol(signal),
        context.get("symbol1"),
        context.get("symbol"),
    ]
    for candidate in candidates:
        symbol = symbol_prefix(str(candidate or ""))
        if symbol and symbol != "UNKNOWN":
            return symbol
    return None


def _shock_size_for_signal(signal: dict[str, Any], score: dict[str, Any] | Any | None) -> float:
    severity = str(signal.get("severity") or "medium").lower()
    base = {
        "critical": 0.10,
        "high": 0.07,
        "medium": 0.05,
        "low": 0.03,
    }.get(severity, 0.05)
    score_value = float(score.get("combined") or score.get("priority") or 0) if isinstance(score, dict) else 0.0
    if score_value >= 85:
        base += 0.02
    elif score_value >= 70:
        base += 0.01
    return min(0.12, base)


def _latest_context_price(context: dict[str, Any]) -> float | None:
    market_data = context.get("market_data")
    if not isinstance(market_data, list) or not market_data:
        return None
    latest = market_data[-1]
    if not isinstance(latest, dict) or latest.get("close") is None:
        return None
    return float(latest["close"])


def _spread_info_from_payload(payload: Any) -> SpreadInfo | None:
    if not isinstance(payload, dict):
        return None
    return SpreadInfo(
        leg1=str(payload["leg1"]),
        leg2=str(payload["leg2"]),
        current_spread=float(payload["current_spread"]),
        historical_mean=float(payload["historical_mean"]),
        sigma1_upper=float(payload["sigma1_upper"]),
        sigma1_lower=float(payload["sigma1_lower"]),
        z_score=float(payload["z_score"]),
        half_life=float(payload["half_life"]),
        adf_p_value=float(payload["adf_p_value"]),
        unit=str(payload.get("unit", "price")),
    )


def recommendation_legs_from_signal(signal: dict[str, Any]) -> list[RecommendationLeg]:
    spread_info = _spread_info_from_payload(signal.get("spread_info"))
    if spread_info is not None:
        if spread_info.z_score > 0:
            return [
                RecommendationLeg(asset=spread_info.leg1, direction="short"),
                RecommendationLeg(asset=spread_info.leg2, direction="long"),
            ]
        return [
            RecommendationLeg(asset=spread_info.leg1, direction="long"),
            RecommendationLeg(asset=spread_info.leg2, direction="short"),
        ]

    directional_leg = directional_trade_leg(signal)
    if directional_leg is not None:
        return [
            RecommendationLeg(
                asset=str(directional_leg["asset"]),
                direction=str(directional_leg["direction"]),
            )
        ]

    return [
        RecommendationLeg(asset=str(asset), direction="watch")
        for asset in signal.get("related_assets", [])
    ]


def recommended_action(signal: dict[str, Any]) -> str:
    if signal.get("spread_info") is not None:
        return "open_spread"
    if directional_trade_leg(signal) is not None:
        return TRADE_PLAN_DIRECTIONAL_ACTION
    return "watchlist_only"


def build_trade_plan_recommendation(
    *,
    alert: Alert,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None,
    event_payload: dict[str, Any],
    triggered_at: datetime,
) -> Recommendation | None:
    return evaluate_trade_plan_candidate(
        alert=alert,
        signal=signal,
        context=context,
        score=score,
        event_payload=event_payload,
        triggered_at=triggered_at,
    ).recommendation


def evaluate_trade_plan_candidate(
    *,
    alert: Alert,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None,
    event_payload: dict[str, Any],
    triggered_at: datetime,
) -> TradePlanCandidateEvaluation:
    raw_action = str(event_payload.get("recommended_action") or "")
    current_action = recommended_action(signal)
    action = current_action if raw_action in {"", "watchlist_only"} else raw_action
    if action not in TRADE_PLAN_ACTIONS:
        if str(signal.get("signal_type") or "unknown") in TRADE_PLAN_DIRECTIONAL_SIGNAL_TYPES:
            return TradePlanCandidateEvaluation(None, "missing_direction")
        return TradePlanCandidateEvaluation(None, "unsupported_action")
    if alert.dedup_suppressed:
        return TradePlanCandidateEvaluation(None, "alert_dedup_suppressed")
    if not adversarial_allows_trade_plan(alert, event_payload):
        return TradePlanCandidateEvaluation(None, "adversarial_failed")
    expires_at = triggered_at + TRADE_PLAN_EXPIRES_AFTER
    if expires_at <= datetime.now(timezone.utc):
        return TradePlanCandidateEvaluation(None, "stale_signal")

    score_payload = score if isinstance(score, dict) else {}
    combined_score = float(score_payload.get("combined") or 0)
    confidence = trade_plan_effective_confidence(
        signal=signal,
        alert=alert,
        event_payload=event_payload,
    )
    if not trade_plan_score_passed(action, combined_score=combined_score, confidence=confidence):
        return TradePlanCandidateEvaluation(None, "score_below_gate")

    legs = executable_trade_legs(event_payload.get("legs"), signal, action=action)
    if len(legs) < min_trade_plan_legs(action):
        return TradePlanCandidateEvaluation(None, "missing_trade_legs")

    direction = str(legs[0].get("direction") or "long")
    entry_price = trade_plan_entry_price(signal, context, legs=legs)
    if entry_price is None:
        return TradePlanCandidateEvaluation(None, "missing_entry_price")
    stop_loss, take_profit = trade_plan_bounds(entry_price, direction)
    risk_items = trade_plan_risk_items(alert, signal, event_payload)
    adversarial_result = adversarial_payload(event_payload)
    if adversarial_result.get("warmup_enabled") is True:
        risk_items.append(
            "Adversarial engine warmup: historical combo is audit-only; confirm before adopting."
        )

    return TradePlanCandidateEvaluation(
        Recommendation(
            id=uuid4(),
            alert_id=alert.id,
            status=trade_plan_status(alert),
            recommended_action=action,
            legs=legs,
            priority_score=float(score_payload.get("priority") or combined_score),
            portfolio_fit_score=float(score_payload.get("portfolio_fit") or 0),
            margin_efficiency_score=float(score_payload.get("margin_efficiency") or 0),
            margin_required=float(event_payload.get("margin_required") or DEFAULT_MARGIN_REQUIRED),
            reasoning=trade_plan_reasoning(alert, combined_score, confidence),
            one_liner=alert.one_liner or alert.summary,
            risk_items=risk_items,
            expires_at=expires_at,
            max_holding_days=TRADE_PLAN_DEFAULT_HOLDING_DAYS,
            position_size_pct=trade_plan_position_size_pct(combined_score, confidence),
            risk_reward_ratio=2.0,
            backtest_summary=trade_plan_backtest_summary(
                alert=alert,
                signal=signal,
                event_payload=event_payload,
                action=action,
            ),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        ),
        None,
    )


def adversarial_allows_trade_plan(alert: Alert, event_payload: dict[str, Any]) -> bool:
    if alert.adversarial_passed:
        return True
    adversarial_result = adversarial_payload(event_payload)
    return (
        adversarial_result.get("warmup_enabled") is True
        and adversarial_result.get("suppressed") is not True
    )


def trade_plan_effective_confidence(
    *,
    signal: dict[str, Any],
    alert: Alert,
    event_payload: dict[str, Any],
) -> float:
    raw_confidence = max(0.0, min(1.0, float(signal.get("confidence") or alert.confidence or 0)))
    adversarial_result = adversarial_payload(event_payload)
    multiplier = positive_float(adversarial_result.get("confidence_multiplier"))
    if (
        adversarial_result.get("warmup_enabled") is True
        and adversarial_result.get("suppressed") is not True
        and multiplier is not None
        and multiplier < 1.0
    ):
        return max(0.0, min(1.0, raw_confidence / multiplier))
    return raw_confidence


def executable_trade_legs(
    raw_legs: Any,
    signal: dict[str, Any],
    *,
    action: str,
) -> list[dict[str, Any]]:
    candidates = raw_legs if isinstance(raw_legs, list) else jsonable(recommendation_legs_from_signal(signal))
    legs: list[dict[str, Any]] = []
    for raw_leg in candidates:
        if not isinstance(raw_leg, dict):
            continue
        asset = str(raw_leg.get("asset") or raw_leg.get("symbol") or "").strip().upper()
        direction = str(raw_leg.get("direction") or "").strip().lower()
        if not asset or direction not in {"long", "short"}:
            continue
        legs.append(
            {
                **raw_leg,
                "asset": asset,
                "direction": direction,
                "lots": float(raw_leg.get("lots") or raw_leg.get("size") or 1),
            }
        )
    if not legs and action == TRADE_PLAN_DIRECTIONAL_ACTION:
        leg = directional_trade_leg(signal)
        if leg is not None:
            legs.append(leg)
    return legs


def directional_trade_leg(signal: dict[str, Any]) -> dict[str, Any] | None:
    signal_type = str(signal.get("signal_type") or "unknown")
    if signal_type not in TRADE_PLAN_DIRECTIONAL_SIGNAL_TYPES:
        return None
    direction = signal_direction(signal)
    if direction == "neutral":
        return None
    asset = primary_symbol(signal).strip().upper()
    if not asset or asset == "UNKNOWN":
        return None
    return {
        "asset": asset,
        "direction": "long" if direction == "bullish" else "short",
        "lots": 1.0,
    }


def trade_plan_score_passed(action: str, *, combined_score: float, confidence: float) -> bool:
    if action == TRADE_PLAN_DIRECTIONAL_ACTION:
        return (
            combined_score >= TRADE_PLAN_MIN_DIRECTIONAL_SCORE
            and confidence >= TRADE_PLAN_MIN_DIRECTIONAL_CONFIDENCE
        )
    return combined_score >= TRADE_PLAN_MIN_COMBINED_SCORE and confidence >= TRADE_PLAN_MIN_CONFIDENCE


async def open_trade_plan_for_candidate(
    session: AsyncSession | None,
    candidate: Recommendation,
    *,
    as_of: datetime | None = None,
) -> Recommendation | None:
    if session is None or trade_plan_match_key(candidate) is None:
        return None
    effective_as_of = as_of or datetime.now(timezone.utc)
    result = await session.scalars(
        select(Recommendation)
        .where(
            Recommendation.status.in_(sorted(TRADE_PLAN_OPEN_STATUSES)),
            Recommendation.expires_at > effective_as_of,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(100)
    )
    rows = result.all() if hasattr(result, "all") else []
    for row in rows:
        if trade_plan_matches(row, candidate):
            return row
    return None


async def open_trade_plan_for_context_signal(
    session: AsyncSession | None,
    signal: dict[str, Any],
    *,
    skip_reason: str | None = None,
    as_of: datetime | None = None,
) -> Recommendation | None:
    if session is None or not trade_plan_context_signal(signal, skip_reason=skip_reason):
        return None
    symbol = primary_symbol(signal).strip().upper()
    if not symbol or symbol == "UNKNOWN":
        return None

    preferred_direction = trade_plan_direction_from_signal(signal)
    effective_as_of = as_of or datetime.now(timezone.utc)
    result = await session.scalars(
        select(Recommendation)
        .where(
            Recommendation.status.in_(sorted(TRADE_PLAN_OPEN_STATUSES)),
            Recommendation.expires_at > effective_as_of,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(100)
    )
    rows = result.all() if hasattr(result, "all") else []
    matches: list[tuple[Recommendation, str]] = []
    for row in rows:
        for leg in row.legs or []:
            if not isinstance(leg, dict):
                continue
            leg_symbol = str(leg.get("asset") or leg.get("symbol") or "").strip().upper()
            leg_direction = str(leg.get("direction") or "").strip().lower()
            if leg_symbol != symbol or leg_direction not in {"long", "short"}:
                continue
            if preferred_direction is not None and leg_direction != preferred_direction:
                continue
            matches.append((row, leg_direction))
            break

    if not matches:
        return None
    if preferred_direction is None and len({direction for _, direction in matches}) > 1:
        return None
    return matches[0][0]


def trade_plan_context_signal(signal: dict[str, Any], *, skip_reason: str | None = None) -> bool:
    signal_type = str(signal.get("signal_type") or "unknown")
    if signal_type in TRADE_PLAN_CONTEXT_SIGNAL_TYPES:
        return True
    return skip_reason == "score_below_gate" and directional_trade_leg(signal) is not None


def trade_plan_direction_from_signal(signal: dict[str, Any]) -> str | None:
    direction = signal_direction(signal)
    if direction == "bullish":
        return "long"
    if direction == "bearish":
        return "short"
    return None


def trade_plan_matches(left: Recommendation, right: Recommendation) -> bool:
    left_key = trade_plan_match_key(left)
    return left_key is not None and left_key == trade_plan_match_key(right)


def trade_plan_match_key(recommendation: Recommendation) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    legs = [
        (str(leg.get("asset") or "").strip().upper(), str(leg.get("direction") or "").strip().lower())
        for leg in recommendation.legs
        if isinstance(leg, dict)
    ]
    normalized = tuple((asset, direction) for asset, direction in legs if asset and direction)
    if not normalized:
        return None
    return recommendation.recommended_action, normalized


def merge_trade_plan_evidence(
    target: Recommendation,
    incoming: Recommendation,
    *,
    alert: Alert,
) -> None:
    target.priority_score = max(float(target.priority_score), float(incoming.priority_score))
    target.portfolio_fit_score = max(float(target.portfolio_fit_score), float(incoming.portfolio_fit_score))
    target.margin_efficiency_score = max(
        float(target.margin_efficiency_score),
        float(incoming.margin_efficiency_score),
    )
    target.margin_required = max(float(target.margin_required), float(incoming.margin_required))
    if incoming.expires_at > target.expires_at:
        target.expires_at = incoming.expires_at
    target.risk_items = compact_trade_plan_risk_items(
        target.risk_items or [],
        incoming.risk_items or [],
    )
    target.backtest_summary = merged_trade_plan_backtest_summary(
        target.backtest_summary,
        incoming.backtest_summary,
        alert=alert,
    )
    target.updated_at = datetime.now(timezone.utc)


def attach_trade_plan_context_evidence(
    target: Recommendation,
    *,
    alert: Alert,
    signal: dict[str, Any],
    skip_reason: str | None,
) -> None:
    target.risk_items = compact_trade_plan_risk_items(
        target.risk_items or [],
        signal.get("risk_items", []),
    )
    target.backtest_summary = context_enriched_trade_plan_summary(
        target.backtest_summary,
        alert=alert,
        signal=signal,
        skip_reason=skip_reason,
    )
    target.updated_at = datetime.now(timezone.utc)


def context_enriched_trade_plan_summary(
    target_summary: dict[str, Any] | None,
    *,
    alert: Alert,
    signal: dict[str, Any],
    skip_reason: str | None,
) -> dict[str, Any]:
    summary = dict(target_summary or {})
    linked_context = list(summary.get("linked_context_alerts") or [])
    alert_payload = {
        "alert_id": str(alert.id),
        "signal_type": alert.type,
        "category": alert.category,
        "status": alert.status,
        "confidence_tier": alert.confidence_tier,
        "skip_reason": skip_reason,
        "title": alert.title,
    }
    if not any(item.get("alert_id") == alert_payload["alert_id"] for item in linked_context if isinstance(item, dict)):
        linked_context.append(alert_payload)

    context_types = {
        str(item.get("signal_type"))
        for item in linked_context
        if isinstance(item, dict) and item.get("signal_type")
    }
    if signal.get("signal_type"):
        context_types.add(str(signal["signal_type"]))

    summary["linked_context_alerts"] = linked_context
    summary["context_signal_types"] = sorted(context_types)
    summary["context_evidence_count"] = len(linked_context)
    summary["context_enriched"] = True
    return summary


def compact_trade_plan_risk_items(*groups: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for raw_item in group:
            item = str(raw_item).strip()
            if not item or item in seen:
                continue
            items.append(item)
            seen.add(item)
            if len(items) >= TRADE_PLAN_MAX_RISK_ITEMS:
                return items
    return items


def merged_trade_plan_backtest_summary(
    target_summary: dict[str, Any] | None,
    incoming_summary: dict[str, Any] | None,
    *,
    alert: Alert,
) -> dict[str, Any]:
    summary = dict(target_summary or {})
    if not summary and isinstance(incoming_summary, dict):
        summary.update(incoming_summary)
    linked_alerts = list(summary.get("linked_supporting_alerts") or [])
    alert_payload = {
        "alert_id": str(alert.id),
        "signal_type": alert.type,
        "category": alert.category,
        "status": alert.status,
        "confidence_tier": alert.confidence_tier,
    }
    if not any(item.get("alert_id") == alert_payload["alert_id"] for item in linked_alerts if isinstance(item, dict)):
        linked_alerts.append(alert_payload)
    evidence_types = {
        str(item.get("signal_type"))
        for item in linked_alerts
        if isinstance(item, dict) and item.get("signal_type")
    }
    if incoming_summary and incoming_summary.get("signal_type"):
        evidence_types.add(str(incoming_summary["signal_type"]))
    if summary.get("signal_type"):
        evidence_types.add(str(summary["signal_type"]))
    summary["linked_supporting_alerts"] = linked_alerts
    summary["evidence_signal_types"] = sorted(evidence_types)
    summary["evidence_count"] = 1 + len(linked_alerts)
    summary["merged_evidence"] = True
    return summary


def min_trade_plan_legs(action: str) -> int:
    return 1 if action == TRADE_PLAN_DIRECTIONAL_ACTION else 2


def trade_plan_entry_price(
    signal: dict[str, Any],
    context: dict[str, Any],
    *,
    legs: list[dict[str, Any]],
) -> float | None:
    for leg in legs:
        entry = positive_float(
            leg.get("entry_price"),
            leg.get("entryPrice"),
            leg.get("current_price"),
            leg.get("currentPrice"),
            leg.get("price"),
        )
        if entry is not None:
            return entry

    latest_price = _latest_context_price(context)
    if latest_price is not None and latest_price > 0:
        return latest_price
    cost_price = _latest_context_cost_price(context, symbol=primary_symbol(signal))
    if cost_price is not None:
        return cost_price
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict):
        current_spread = float(spread_info.get("current_spread") or 0)
        if current_spread != 0:
            return max(abs(current_spread), 1.0)
    return None


def _latest_context_cost_price(context: dict[str, Any], *, symbol: str) -> float | None:
    snapshots = context.get("cost_snapshots")
    if not isinstance(snapshots, list):
        return None
    normalized_symbol = symbol.strip().upper()
    for row in reversed(snapshots):
        if not isinstance(row, dict):
            continue
        row_symbol = str(row.get("symbol") or "").strip().upper()
        if normalized_symbol and row_symbol and row_symbol != normalized_symbol:
            continue
        price = positive_float(row.get("current_price"), row.get("price"), row.get("close"))
        if price is not None:
            return price
    return None


def positive_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def trade_plan_status(alert: Alert) -> str:
    if alert.status == "active" and not alert.human_action_required:
        return "pending"
    return "pending_review"


def trade_plan_bounds(entry_price: float, direction: str) -> tuple[float, float]:
    if direction == "short":
        return round(entry_price * 1.03, 4), round(entry_price * 0.94, 4)
    return round(entry_price * 0.97, 4), round(entry_price * 1.06, 4)


def trade_plan_position_size_pct(combined_score: float, confidence: float) -> float:
    raw = 0.02 + max(0.0, combined_score - TRADE_PLAN_MIN_COMBINED_SCORE) * 0.001 + max(
        0.0, confidence - TRADE_PLAN_MIN_CONFIDENCE
    ) * 0.05
    return round(min(0.05, raw), 4)


def trade_plan_risk_items(
    alert: Alert,
    signal: dict[str, Any],
    event_payload: dict[str, Any],
) -> list[str]:
    items = [
        str(item)
        for item in [
            *list(signal.get("risk_items") or []),
            *list(signal.get("manual_check_items") or []),
        ]
        if item
    ]
    adversarial_result = adversarial_payload(event_payload)
    if adversarial_result.get("runtime_mode"):
        items.append(f"Adversarial runtime: {adversarial_result['runtime_mode']}.")
    restored_confidence = restored_warmup_confidence(signal, alert, event_payload)
    if restored_confidence is not None:
        items.append(
            "Warmup confidence restored for trade-plan gating: "
            f"{restored_confidence[0]:.0%} -> {restored_confidence[1]:.0%}."
        )
    review_reasons = trade_plan_review_reasons(alert, event_payload)
    if review_reasons:
        items.append("复核原因：" + "；".join(review_reasons))
    return sorted(set(items))


def restored_warmup_confidence(
    signal: dict[str, Any],
    alert: Alert,
    event_payload: dict[str, Any],
) -> tuple[float, float] | None:
    raw_confidence = max(0.0, min(1.0, float(signal.get("confidence") or alert.confidence or 0)))
    effective_confidence = trade_plan_effective_confidence(
        signal=signal,
        alert=alert,
        event_payload=event_payload,
    )
    if effective_confidence > raw_confidence:
        return raw_confidence, effective_confidence
    return None


def trade_plan_reasoning(alert: Alert, combined_score: float, confidence: float) -> str:
    return (
        f"{alert.title}: score {combined_score:.0f}, confidence {confidence:.0%}, "
        "adversarial checks passed and Alert Agent marked it actionable."
    )


def trade_plan_backtest_summary(
    *,
    alert: Alert,
    signal: dict[str, Any],
    event_payload: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    adversarial_result = adversarial_payload(event_payload)
    spread_info = signal.get("spread_info") if isinstance(signal.get("spread_info"), dict) else {}
    alert_route = alert_route_payload(event_payload)
    review_reasons = trade_plan_review_reasons(alert, event_payload)
    return {
        "source": "signal_scored_trade_plan_gate",
        "recommended_action": action,
        "signal_type": signal.get("signal_type"),
        "effective_confidence": trade_plan_effective_confidence(
            signal=signal,
            alert=alert,
            event_payload=event_payload,
        ),
        "sample_size": int(adversarial_result.get("historical_combo_sample_size") or 0),
        "adversarial_runtime_mode": adversarial_result.get("runtime_mode"),
        "historical_combo_mode": adversarial_result.get("historical_combo_mode"),
        "spread_z_score": spread_info.get("z_score"),
        "spread_half_life": spread_info.get("half_life"),
        "review_required": bool(alert.human_action_required or alert.status != "active"),
        "review_reasons": review_reasons,
        "alert_status": alert.status,
        "confidence_tier": alert.confidence_tier,
        "llm_involved": alert.llm_involved,
        "alert_route": alert_route.get("route"),
        "alert_route_reasons": alert_route.get("reasons", []),
    }


def alert_route_payload(event_payload: dict[str, Any]) -> dict[str, Any]:
    route = event_payload.get("alert_route")
    return route if isinstance(route, dict) else {}


def trade_plan_review_reasons(alert: Alert, event_payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    route = alert_route_payload(event_payload)
    raw_reasons = route.get("reasons")
    if isinstance(raw_reasons, list):
        for reason in raw_reasons:
            label = trade_plan_review_reason_label(str(reason))
            if label is not None:
                reasons.append(label)

    if alert.status != "active":
        reasons.append(f"预警状态为 {alert.status}，不能直接采纳")
    if alert.human_action_required:
        reasons.append("Alert Agent 标记需要人工复核")
    if alert.confidence_tier == "confirm":
        reasons.append("置信度处于确认档")
    elif alert.confidence_tier == "notify" and alert.human_action_required:
        reasons.append("通知档信号被治理规则升级为复核")
    if alert.llm_involved:
        reasons.append("LLM 仲裁参与，需人工确认结论")

    return sorted(set(reasons))


def trade_plan_review_reason_label(reason: str) -> str | None:
    mapping = {
        "direction_conflict": "存在方向冲突",
        "fuzzy_confidence": "置信度处于模糊区间",
        "no_calibration_history": "缺少该信号/品类/行情状态的历史校准样本",
        "cross_sector_chain": "跨板块影响链较长",
        "feedback_caution": "历史反馈提示谨慎",
    }
    if reason.startswith("confidence:confirm"):
        return "置信度处于确认档"
    if reason.startswith("confidence:notify"):
        return "置信度处于通知档"
    if reason.startswith("confidence:auto"):
        return "自动档信号仍被治理规则复核"
    if reason.startswith("classification:"):
        return None
    return mapping.get(reason)


def adversarial_payload(event_payload: dict[str, Any]) -> dict[str, Any]:
    value = event_payload.get("adversarial_result")
    return value if isinstance(value, dict) else {}


def position_conflict_warnings(
    legs: list[RecommendationLeg],
    open_positions: list[PositionGroup],
) -> list[str]:
    warnings: list[str] = []
    for leg in legs:
        if leg.direction not in {"long", "short"}:
            continue
        for position in open_positions:
            for existing in position.legs:
                if existing.asset != leg.asset or existing.direction not in {"long", "short"}:
                    continue
                if existing.direction != leg.direction:
                    warnings.append(
                        f"Position conflict: {leg.asset} signal is {leg.direction}, "
                        f"open position is {existing.direction}."
                    )
    return sorted(set(warnings))


def boost_priority_for_position_signal(score: CombinedScore, *, boost: int) -> CombinedScore:
    priority = min(100, score.priority + boost)
    combined = round(priority * 0.4 + score.portfolio_fit * 0.3 + score.margin_efficiency * 0.3)
    return CombinedScore(
        priority=priority,
        portfolio_fit=score.portfolio_fit,
        margin_efficiency=score.margin_efficiency,
        combined=combined,
    )


async def open_positions_for_scoring(
    session: AsyncSession | None,
    payload: dict[str, Any],
) -> list[PositionGroup]:
    if "open_positions" in payload:
        return [
            PositionGroup(
                legs=[
                    RecommendationLeg(
                        asset=str(leg.get("asset") or leg.get("symbol")),
                        direction=str(leg.get("direction", "watch")),
                        lots=float(leg.get("lots", 1)),
                    )
                    for leg in position.get("legs", [])
                ]
            )
            for position in payload["open_positions"]
        ]
    if session is None:
        return []

    rows = (await session.scalars(select(Position).where(Position.status == "open"))).all()
    return [
        PositionGroup(
            legs=[
                RecommendationLeg(
                    asset=str(leg.get("asset") or leg.get("symbol")),
                    direction=str(leg.get("direction", "watch")),
                    lots=float(leg.get("lots", 1)),
                )
                for leg in row.legs
            ]
        )
        for row in rows
    ]


async def attach_alert_to_signal_track(
    session: AsyncSession,
    signal_track_id: str | None,
    alert: Alert,
) -> None:
    if signal_track_id is None:
        return

    row = await session.get(SignalTrack, UUID(signal_track_id))
    if row is not None:
        row.alert_id = alert.id
