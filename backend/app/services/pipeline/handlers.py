import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
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
TRADE_PLAN_ACTIONS = {"open_spread"}
TRADE_PLAN_MIN_COMBINED_SCORE = 80.0
TRADE_PLAN_MIN_CONFIDENCE = 0.70
TRADE_PLAN_DEFAULT_HOLDING_DAYS = 20
TRADE_PLAN_EXPIRES_AFTER = timedelta(days=1)

logger = logging.getLogger(__name__)


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
    triggered_at = _parse_datetime(event.payload.get("context", {}).get("timestamp"))
    score = event.payload.get("score", {})
    context = event.payload.get("context", {})
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
    recommendation = build_trade_plan_recommendation(
        alert=alert,
        signal=signal,
        context=context,
        score=score,
        event_payload=event.payload,
        triggered_at=triggered_at,
    )
    if recommendation is not None:
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

    return [
        RecommendationLeg(asset=str(asset), direction="watch")
        for asset in signal.get("related_assets", [])
    ]


def recommended_action(signal: dict[str, Any]) -> str:
    if signal.get("spread_info") is not None:
        return "open_spread"
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
    action = str(event_payload.get("recommended_action") or recommended_action(signal))
    if action not in TRADE_PLAN_ACTIONS:
        return None
    if alert.dedup_suppressed:
        return None
    if not alert.adversarial_passed:
        return None
    expires_at = triggered_at + TRADE_PLAN_EXPIRES_AFTER
    if expires_at <= datetime.now(timezone.utc):
        return None

    score_payload = score if isinstance(score, dict) else {}
    combined_score = float(score_payload.get("combined") or 0)
    confidence = float(signal.get("confidence") or alert.confidence or 0)
    if combined_score < TRADE_PLAN_MIN_COMBINED_SCORE or confidence < TRADE_PLAN_MIN_CONFIDENCE:
        return None

    legs = executable_trade_legs(event_payload.get("legs"), signal)
    if len(legs) < 2:
        return None

    direction = str(legs[0].get("direction") or "long")
    entry_price = trade_plan_entry_price(signal, context)
    stop_loss, take_profit = trade_plan_bounds(entry_price, direction)
    risk_items = trade_plan_risk_items(signal, event_payload)
    adversarial_result = adversarial_payload(event_payload)
    if adversarial_result.get("warmup_enabled") is True:
        risk_items.append(
            "Adversarial engine warmup: historical combo is audit-only; confirm before adopting."
        )

    return Recommendation(
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
        backtest_summary=trade_plan_backtest_summary(signal, event_payload),
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def executable_trade_legs(raw_legs: Any, signal: dict[str, Any]) -> list[dict[str, Any]]:
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
    return legs


def trade_plan_entry_price(signal: dict[str, Any], context: dict[str, Any]) -> float:
    latest_price = _latest_context_price(context)
    if latest_price is not None and latest_price > 0:
        return latest_price
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict):
        current_spread = float(spread_info.get("current_spread") or 0)
        if current_spread != 0:
            return max(abs(current_spread), 1.0)
    return 1.0


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


def trade_plan_risk_items(signal: dict[str, Any], event_payload: dict[str, Any]) -> list[str]:
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
    return sorted(set(items))


def trade_plan_reasoning(alert: Alert, combined_score: float, confidence: float) -> str:
    return (
        f"{alert.title}: score {combined_score:.0f}, confidence {confidence:.0%}, "
        "adversarial checks passed and Alert Agent marked it actionable."
    )


def trade_plan_backtest_summary(
    signal: dict[str, Any],
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    adversarial_result = adversarial_payload(event_payload)
    spread_info = signal.get("spread_info") if isinstance(signal.get("spread_info"), dict) else {}
    return {
        "source": "signal_scored_trade_plan_gate",
        "signal_type": signal.get("signal_type"),
        "sample_size": int(adversarial_result.get("historical_combo_sample_size") or 0),
        "adversarial_runtime_mode": adversarial_result.get("runtime_mode"),
        "historical_combo_mode": adversarial_result.get("historical_combo_mode"),
        "spread_z_score": spread_info.get("z_score"),
        "spread_half_life": spread_info.get("half_life"),
    }


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
