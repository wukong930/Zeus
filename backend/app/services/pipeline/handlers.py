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
from app.models.signal import SignalTrack
from app.services.adversarial.engine import (
    attach_signal_track_to_adversarial_result,
    evaluate_adversarial_signal,
)
from app.services.alert_agent.dedup import check_alert_dedup, record_alert_emitted
from app.services.alert_agent.router import route_alert
from app.services.calibration.tracker import get_calibration_weight, track_signal_emission
from app.services.scoring.engine import CombinedScore, apply_calibration_weight, score_recommendation
from app.services.scoring.portfolio_fit import PositionGroup, RecommendationLeg
from app.services.scenarios import ScenarioRequest, run_scenario_simulation
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

EventPublisher = Callable[..., Awaitable[ZeusEvent]]

DEFAULT_ACCOUNT_NET_VALUE = 1_000_000.0
DEFAULT_MARGIN_REQUIRED = 100_000.0
NEWS_EVENT_SIGNAL_TYPES = {"news_event", "rubber_supply_shock"}


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
    for raw_context in contexts_payload:
        context = trigger_context_from_payload(raw_context)
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
    contexts = [trigger_context_from_payload(raw) for raw in raw_contexts]
    if not contexts:
        return []

    signal_detector = detector or SignalDetector()
    published: list[ZeusEvent] = []
    for raw_context, context in zip(raw_contexts, contexts, strict=False):
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
    alert = Alert(
        id=alert_id,
        title=str(signal["title"]),
        summary=agent_decision.narrative,
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

    await record_alert_emitted(
        session,
        signal=signal,
        signal_combination_hash=event.payload.get("adversarial_result", {}).get(
            "signal_combination_hash"
        ),
        emitted_at=triggered_at,
        score=score,
    )

    return await publisher(
        "alert.created",
        {
            "alert_id": str(alert.id),
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

    report = run_scenario_simulation(
        ScenarioRequest(
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
    )
    return await publisher(
        "scenario.completed",
        {"report": report.to_dict()},
        source="scenario-simulator",
        correlation_id=event.correlation_id,
        session=session,
    )


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
