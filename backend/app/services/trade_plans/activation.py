from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.models.alert import Alert
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.services.alert_agent.dedup import primary_symbol
from app.services.pipeline.handlers import (
    TRADE_PLAN_EXPIRES_AFTER,
    TRADE_PLAN_CONTEXT_SKIP_REASONS,
    attach_trade_plan_context_evidence,
    evaluate_trade_plan_candidate,
    merge_trade_plan_evidence,
    open_trade_plan_for_context_signal,
    open_trade_plan_for_candidate,
    trade_plan_match_key,
)

ALERT_RESULT_CHANNELS = ("alert.created", "alert.suppressed")


@dataclass
class TradePlanActivationResult:
    scanned: int = 0
    created: int = 0
    linked_existing: int = 0
    linked_context: int = 0
    merged_duplicates: int = 0
    skipped_existing: int = 0
    skipped_missing_alert: int = 0
    skipped_ineligible: int = 0
    skipped_stale: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

    def record_skip(self, reason: str) -> None:
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1

    def to_dict(self) -> dict[str, int | str | dict[str, int]]:
        return {
            "status": "completed",
            "scanned": self.scanned,
            "created": self.created,
            "linked_existing": self.linked_existing,
            "linked_context": self.linked_context,
            "merged_duplicates": self.merged_duplicates,
            "skipped_existing": self.skipped_existing,
            "skipped_missing_alert": self.skipped_missing_alert,
            "skipped_ineligible": self.skipped_ineligible,
            "skipped_stale": self.skipped_stale,
            "skip_reasons": dict(sorted(self.skip_reasons.items())),
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
    scored_events = await load_actionable_scored_events(session, limit=limit, as_of=now)

    for scored_event in scored_events:
        result.scanned += 1
        alert = await alert_for_scored_event(session, scored_event)
        if alert is None:
            result.skipped_missing_alert += 1
            result.record_skip("missing_alert")
            continue

        existing = await existing_recommendation_for_alert(session, alert)
        if existing is not None:
            if alert.related_recommendation_id is None:
                alert.related_recommendation_id = existing.id
                result.linked_existing += 1
            else:
                result.skipped_existing += 1
                result.record_skip("existing_recommendation")
            continue

        if alert.dedup_suppressed or alert.status == "suppressed":
            result.skipped_ineligible += 1
            result.record_skip("alert_dedup_suppressed")
            continue

        if alert.expires_at is not None and aware_utc(alert.expires_at) <= aware_utc(now):
            result.skipped_stale += 1
            result.record_skip("stale_alert")
            continue

        payload = dict(scored_event.payload or {})
        signal = payload.get("signal")
        context = payload.get("context")
        if not isinstance(signal, dict) or not isinstance(context, dict):
            result.skipped_ineligible += 1
            result.record_skip("malformed_payload")
            continue

        evaluation = evaluate_trade_plan_candidate(
            alert=alert,
            signal=signal,
            context=context,
            score=payload.get("score", {}),
            event_payload=payload,
            triggered_at=alert.triggered_at,
        )
        recommendation = evaluation.recommendation
        if recommendation is None:
            if evaluation.skip_reason in TRADE_PLAN_CONTEXT_SKIP_REASONS:
                context_plan = await open_trade_plan_for_context_signal(
                    session,
                    signal,
                    skip_reason=evaluation.skip_reason,
                    as_of=now,
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
                            "backfilled": True,
                        },
                        source="trade-plan-activation",
                        correlation_id=scored_event.correlation_id,
                        session=session,
                    )
                    result.linked_context += 1
                    continue
            result.skipped_ineligible += 1
            result.record_skip(evaluation.skip_reason or "ineligible")
            continue

        existing_plan = await open_trade_plan_for_candidate(session, recommendation, as_of=now)
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
                    "backfilled": True,
                },
                source="trade-plan-activation",
                correlation_id=scored_event.correlation_id,
                session=session,
            )
            result.linked_existing += 1
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

    result.merged_duplicates += await merge_open_trade_plan_duplicates(session, as_of=now)
    await session.flush()
    return result


async def load_actionable_scored_events(
    session: AsyncSession,
    *,
    limit: int,
    as_of: datetime | None = None,
) -> list[EventLog]:
    effective_as_of = aware_utc(as_of or datetime.now(timezone.utc))
    scan_limit = max(limit, limit * 5)
    rows = await session.scalars(
        actionable_scored_events_statement(limit=scan_limit, as_of=effective_as_of)
    )
    return live_trade_plan_scored_events(
        list(rows.all()),
        limit=limit,
        as_of=effective_as_of,
    )


def actionable_scored_events_statement(*, limit: int, as_of: datetime | None = None):
    effective_as_of = aware_utc(as_of or datetime.now(timezone.utc))
    window_start = effective_as_of - TRADE_PLAN_EXPIRES_AFTER
    return (
        select(EventLog)
        .where(
            EventLog.channel == "signal.scored",
            EventLog.status == "handled",
            EventLog.created_at >= window_start,
        )
        .order_by(EventLog.created_at.desc())
        .limit(limit)
    )


def live_trade_plan_scored_events(
    rows: list[EventLog],
    *,
    limit: int,
    as_of: datetime | None = None,
) -> list[EventLog]:
    effective_as_of = aware_utc(as_of or datetime.now(timezone.utc))
    live_rows = [
        row
        for row in rows
        if scored_event_effective_at(row) + TRADE_PLAN_EXPIRES_AFTER > effective_as_of
    ]
    return live_rows[:limit]


def scored_event_effective_at(row: EventLog) -> datetime:
    payload = row.payload if isinstance(row.payload, dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    for key in ("freshness_timestamp", "timestamp"):
        parsed = parse_payload_datetime(context.get(key))
        if parsed is not None:
            return parsed
    return aware_utc(row.created_at)


def parse_payload_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return aware_utc(parsed)


async def alert_for_scored_event(session: AsyncSession, scored_event: EventLog) -> Alert | None:
    payload = scored_event.payload if isinstance(scored_event.payload, dict) else {}
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    signal_type = str(signal.get("signal_type") or "")
    symbol = primary_symbol(signal)
    created_event = await session.scalar(
        select(EventLog)
        .where(
            EventLog.channel.in_(ALERT_RESULT_CHANNELS),
            EventLog.correlation_id == scored_event.correlation_id,
            EventLog.payload["signal_type"].as_string() == signal_type,
            EventLog.payload["related_assets"][0].as_string() == symbol,
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


async def existing_recommendation_for_alert(
    session: AsyncSession,
    alert: Alert,
) -> Recommendation | None:
    direct = await recommendation_for_alert(session, alert.id)
    if direct is not None:
        return direct
    if alert.related_recommendation_id is None:
        return None
    return await session.get(Recommendation, alert.related_recommendation_id)


async def merge_open_trade_plan_duplicates(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
) -> int:
    effective_as_of = aware_utc(as_of or datetime.now(timezone.utc))
    rows = (
        await session.scalars(
            select(Recommendation)
            .where(
                Recommendation.status.in_(("pending", "pending_review")),
                Recommendation.expires_at > effective_as_of,
            )
            .order_by(Recommendation.created_at.asc(), Recommendation.id.asc())
        )
    ).all()
    primary_by_key: dict[tuple[str, tuple[tuple[str, str], ...]], Recommendation] = {}
    merged = 0
    for row in rows:
        key = trade_plan_match_key(row)
        if key is None:
            continue
        primary = primary_by_key.get(key)
        if primary is None:
            primary_by_key[key] = row
            continue
        await merge_duplicate_trade_plan(session, primary=primary, duplicate=row)
        merged += 1
    if merged:
        await session.flush()
    return merged


async def merge_duplicate_trade_plan(
    session: AsyncSession,
    *,
    primary: Recommendation,
    duplicate: Recommendation,
) -> None:
    duplicate_alert = (
        await session.get(Alert, duplicate.alert_id) if duplicate.alert_id is not None else None
    )
    if duplicate_alert is not None:
        merge_trade_plan_evidence(primary, duplicate, alert=duplicate_alert)
        duplicate_alert.related_recommendation_id = primary.id
    else:
        primary.risk_items = sorted({*list(primary.risk_items or []), *list(duplicate.risk_items or [])})
        primary.priority_score = max(float(primary.priority_score), float(duplicate.priority_score))
        primary.updated_at = effective_now()

    linked_alerts = (
        await session.scalars(
            select(Alert).where(Alert.related_recommendation_id == duplicate.id)
        )
    ).all()
    for alert in linked_alerts:
        alert.related_recommendation_id = primary.id

    duplicate.status = "ignored"
    duplicate.ignored_reason = f"Merged into active recommendation {primary.id}."
    summary = dict(duplicate.backtest_summary or {})
    summary["merged_into_recommendation_id"] = str(primary.id)
    duplicate.backtest_summary = summary
    duplicate.updated_at = effective_now()


def effective_now() -> datetime:
    return datetime.now(timezone.utc)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
