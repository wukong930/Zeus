from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.alert import Alert
from app.models.alert_agent import AlertDedupCache
from app.services.signals.outcomes import direction_from_signal

DEFAULT_REPEAT_WINDOW_HOURS = 12
DEFAULT_COMBINATION_WINDOW_HOURS = 24
DEFAULT_DAILY_ALERT_LIMIT = 50

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class AlertDedupDecision:
    suppressed: bool
    reason: str | None = None
    symbol: str | None = None
    direction: str | None = None
    evaluator: str | None = None


async def check_alert_dedup(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None,
    signal_combination_hash: str | None = None,
    as_of: datetime | None = None,
    daily_limit: int = DEFAULT_DAILY_ALERT_LIMIT,
) -> AlertDedupDecision:
    symbol = primary_symbol(signal)
    direction = signal_direction(signal)
    evaluator = str(signal.get("signal_type") or "unknown")
    if session is None:
        return AlertDedupDecision(False, symbol=symbol, direction=direction, evaluator=evaluator)

    effective_at = as_of or datetime.now(timezone.utc)
    severity = str(signal.get("severity") or "low")
    severity_rank = SEVERITY_RANK.get(severity, 1)

    try:
        same_key = (
            await session.scalars(
                select(AlertDedupCache)
                .where(
                    AlertDedupCache.symbol == symbol,
                    AlertDedupCache.direction == direction,
                    AlertDedupCache.evaluator == evaluator,
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return AlertDedupDecision(False, symbol=symbol, direction=direction, evaluator=evaluator)

    if same_key is not None:
        recent = same_key.last_emitted_at >= effective_at - timedelta(hours=DEFAULT_REPEAT_WINDOW_HOURS)
        if recent and severity_rank <= SEVERITY_RANK.get(same_key.last_severity, 1):
            return AlertDedupDecision(
                True,
                reason="same_symbol_direction_evaluator",
                symbol=symbol,
                direction=direction,
                evaluator=evaluator,
            )

    if signal_combination_hash:
        same_hash = (
            await session.scalars(
                select(AlertDedupCache)
                .where(AlertDedupCache.signal_combination_hash == signal_combination_hash)
                .limit(1)
            )
        ).first()
        if same_hash is not None:
            recent_hash = same_hash.last_emitted_at >= effective_at - timedelta(
                hours=DEFAULT_COMBINATION_WINDOW_HOURS
            )
            if recent_hash and severity_rank <= SEVERITY_RANK.get(same_hash.last_severity, 1):
                return AlertDedupDecision(
                    True,
                    reason="same_signal_combination",
                    symbol=symbol,
                    direction=direction,
                    evaluator=evaluator,
                )

    if await daily_limit_reached(session, as_of=effective_at, daily_limit=daily_limit):
        score_value = combined_score(score)
        if score_value < 90:
            return AlertDedupDecision(
                True,
                reason="daily_limit",
                symbol=symbol,
                direction=direction,
                evaluator=evaluator,
            )

    return AlertDedupDecision(False, symbol=symbol, direction=direction, evaluator=evaluator)


async def record_alert_emitted(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    signal_combination_hash: str | None,
    emitted_at: datetime | None = None,
    score: dict[str, Any] | Any | None = None,
) -> None:
    if session is None:
        return
    effective_at = emitted_at or datetime.now(timezone.utc)
    symbol = primary_symbol(signal)
    direction = signal_direction(signal)
    evaluator = str(signal.get("signal_type") or "unknown")
    try:
        row = (
            await session.scalars(
                select(AlertDedupCache)
                .where(
                    AlertDedupCache.symbol == symbol,
                    AlertDedupCache.direction == direction,
                    AlertDedupCache.evaluator == evaluator,
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        raise

    if row is None:
        row = AlertDedupCache(
            symbol=symbol,
            direction=direction,
            evaluator=evaluator,
            signal_combination_hash=signal_combination_hash,
            last_emitted_at=effective_at,
            last_severity=str(signal.get("severity") or "low"),
            last_score=int(combined_score(score)),
            hit_count=1,
            details={"title": signal.get("title")},
        )
        session.add(row)
    else:
        row.signal_combination_hash = signal_combination_hash
        row.last_emitted_at = effective_at
        row.last_severity = str(signal.get("severity") or "low")
        row.last_score = int(combined_score(score))
        row.hit_count = int(row.hit_count or 0) + 1
        row.details = {"title": signal.get("title")}
        row.updated_at = effective_at
    await session.flush()


async def daily_limit_reached(
    session: AsyncSession,
    *,
    as_of: datetime,
    daily_limit: int,
) -> bool:
    try:
        day_start = datetime.combine(as_of.date(), time.min, tzinfo=as_of.tzinfo or timezone.utc)
        count = await session.scalar(
            select(func.count(Alert.id)).where(
                Alert.triggered_at >= day_start,
                Alert.status == "active",
            )
        )
    except Exception:
        await rollback_if_possible(session)
        return False
    return int(count or 0) >= daily_limit


def primary_symbol(signal: dict[str, Any]) -> str:
    related_assets = signal.get("related_assets") or []
    if related_assets:
        return str(related_assets[0])
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("leg1") is not None:
        return str(spread_info["leg1"])
    return "UNKNOWN"


def signal_direction(signal: dict[str, Any]) -> str:
    direction = direction_from_signal(signal)
    if direction > 0:
        return "bullish"
    if direction < 0:
        return "bearish"
    return "neutral"


def combined_score(score: dict[str, Any] | Any | None) -> float:
    if score is None:
        return 0.0
    if isinstance(score, dict):
        return float(score.get("combined") or score.get("priority") or 0)
    return float(getattr(score, "combined", getattr(score, "priority", 0)) or 0)
