from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ZeusEvent, publish
from app.models.alert import Alert
from app.models.position import Position
from app.services.scoring.engine import score_recommendation
from app.services.scoring.portfolio_fit import PositionGroup, RecommendationLeg
from app.services.signals.detector import SignalDetector
from app.services.signals.types import (
    IndustryPoint,
    MarketBar,
    SpreadInfo,
    SpreadStatistics,
    TriggerContext,
)

EventPublisher = Callable[..., Awaitable[ZeusEvent]]

DEFAULT_ACCOUNT_NET_VALUE = 1_000_000.0
DEFAULT_MARGIN_REQUIRED = 100_000.0


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


async def handle_market_update(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    detector: SignalDetector | None = None,
    publisher: EventPublisher = publish,
) -> list[ZeusEvent]:
    contexts = [trigger_context_from_payload(raw) for raw in trigger_context_payloads(event)]
    if not contexts:
        return []

    signal_detector = detector or SignalDetector()
    published: list[ZeusEvent] = []
    for context in contexts:
        results = await signal_detector.detect(context)
        for result in results:
            published.append(
                await publisher(
                    "signal.detected",
                    {
                        "signal": jsonable(result),
                        "context": jsonable(context),
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

    spread_info = _spread_info_from_payload(signal.get("spread_info"))
    legs = recommendation_legs_from_signal(signal)
    open_positions = await open_positions_for_scoring(session, event.payload)
    margin_required = float(event.payload.get("margin_required", DEFAULT_MARGIN_REQUIRED))
    account_net_value = float(event.payload.get("account_net_value", DEFAULT_ACCOUNT_NET_VALUE))
    score = score_recommendation(
        spread_info=spread_info,
        confidence=float(signal.get("confidence", 0)),
        legs=legs,
        open_positions=open_positions,
        margin_required=margin_required,
        account_net_value=account_net_value,
    )

    return await publisher(
        "signal.scored",
        {
            "signal": signal,
            "context": event.payload.get("context", {}),
            "score": jsonable(score),
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
    alert = Alert(
        id=alert_id,
        title=str(signal["title"]),
        summary=str(signal["summary"]),
        severity=str(signal["severity"]),
        category=str(event.payload.get("context", {}).get("category") or "unknown"),
        type=str(signal["signal_type"]),
        status="active",
        triggered_at=triggered_at,
        expires_at=triggered_at + timedelta(days=1),
        confidence=float(signal.get("confidence", 0)),
        related_assets=list(signal.get("related_assets", [])),
        spread_info=signal.get("spread_info"),
        trigger_chain=list(signal.get("trigger_chain", [])),
        risk_items=list(signal.get("risk_items", [])),
        manual_check_items=list(signal.get("manual_check_items", [])),
        one_liner=f"Priority {score.get('priority', 0)} / combined {score.get('combined', 0)}.",
    )
    session.add(alert)
    await session.flush()

    return await publisher(
        "alert.created",
        {
            "alert_id": str(alert.id),
            "signal_type": alert.type,
            "severity": alert.severity,
            "category": alert.category,
            "score": score,
            "related_assets": alert.related_assets,
        },
        source="alert-service",
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
