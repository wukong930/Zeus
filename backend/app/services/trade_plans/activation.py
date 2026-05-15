from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.models.alert import Alert
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.services.pipeline.handlers import build_trade_plan_recommendation


@dataclass
class TradePlanActivationResult:
    scanned: int = 0
    created: int = 0
    linked_existing: int = 0
    skipped_existing: int = 0
    skipped_missing_alert: int = 0
    skipped_ineligible: int = 0
    skipped_stale: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return {
            "status": "completed",
            "scanned": self.scanned,
            "created": self.created,
            "linked_existing": self.linked_existing,
            "skipped_existing": self.skipped_existing,
            "skipped_missing_alert": self.skipped_missing_alert,
            "skipped_ineligible": self.skipped_ineligible,
            "skipped_stale": self.skipped_stale,
        }


async def sync_trade_plan_recommendations(
    session: AsyncSession,
    *,
    limit: int = 100,
    publisher=publish,
    as_of: datetime | None = None,
) -> TradePlanActivationResult:
    """Recover missing trade-plan rows from handled actionable signal events."""
    now = as_of or datetime.now(timezone.utc)
    result = TradePlanActivationResult()
    scored_events = await load_actionable_scored_events(session, limit=limit)

    for scored_event in scored_events:
        result.scanned += 1
        alert = await alert_for_scored_event(session, scored_event)
        if alert is None:
            result.skipped_missing_alert += 1
            continue

        existing = await recommendation_for_alert(session, alert.id)
        if existing is not None:
            if alert.related_recommendation_id is None:
                alert.related_recommendation_id = existing.id
                result.linked_existing += 1
            else:
                result.skipped_existing += 1
            continue

        if alert.expires_at is not None and aware_utc(alert.expires_at) <= aware_utc(now):
            result.skipped_stale += 1
            continue

        payload = dict(scored_event.payload or {})
        signal = payload.get("signal")
        context = payload.get("context")
        if not isinstance(signal, dict) or not isinstance(context, dict):
            result.skipped_ineligible += 1
            continue

        recommendation = build_trade_plan_recommendation(
            alert=alert,
            signal=signal,
            context=context,
            score=payload.get("score", {}),
            event_payload=payload,
            triggered_at=alert.triggered_at,
        )
        if recommendation is None:
            result.skipped_ineligible += 1
            continue

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
                "backfilled": True,
            },
            source="trade-plan-activation",
            correlation_id=scored_event.correlation_id,
            session=session,
        )
        result.created += 1

    await session.flush()
    return result


async def load_actionable_scored_events(session: AsyncSession, *, limit: int) -> list[EventLog]:
    action = EventLog.payload["recommended_action"].as_string()
    rows = await session.scalars(
        select(EventLog)
        .where(
            EventLog.channel == "signal.scored",
            EventLog.status == "handled",
            action == "open_spread",
        )
        .order_by(EventLog.created_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def alert_for_scored_event(session: AsyncSession, scored_event: EventLog) -> Alert | None:
    created_event = await session.scalar(
        select(EventLog)
        .where(
            EventLog.channel == "alert.created",
            EventLog.correlation_id == scored_event.correlation_id,
        )
        .order_by(EventLog.created_at.desc())
        .limit(1)
    )
    alert_id = alert_id_from_event(created_event)
    if alert_id is None:
        return None
    return await session.get(Alert, alert_id)


def alert_id_from_event(event: EventLog | None) -> UUID | None:
    if event is None:
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    value = payload.get("alert_id")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


async def recommendation_for_alert(session: AsyncSession, alert_id: UUID) -> Recommendation | None:
    return await session.scalar(
        select(Recommendation)
        .where(Recommendation.alert_id == alert_id)
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
