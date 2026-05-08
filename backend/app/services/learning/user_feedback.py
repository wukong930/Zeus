from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.alert import Alert
from app.models.user_feedback import UserFeedback


@dataclass(frozen=True)
class FeedbackSummary:
    signal_type: str
    agree_count: int
    disagree_count: int
    uncertain_count: int
    will_trade_count: int


@dataclass(frozen=True)
class FeedbackHint:
    signal_type: str
    hint: str
    agree_count: int
    disagree_count: int


async def record_user_feedback(
    session: AsyncSession,
    *,
    alert_id: UUID | None,
    recommendation_id: UUID | None = None,
    agree: str,
    will_trade: str,
    disagreement_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> UserFeedback:
    alert = await session.get(Alert, alert_id) if alert_id is not None else None
    row = UserFeedback(
        alert_id=alert_id,
        recommendation_id=recommendation_id,
        signal_type=alert.type if alert is not None else None,
        category=alert.category if alert is not None else None,
        agree=agree,
        disagreement_reason=disagreement_reason,
        will_trade=will_trade,
        metadata_json=metadata or {},
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


async def feedback_summary_by_signal_type(
    session: AsyncSession,
    *,
    signal_type: str,
) -> FeedbackSummary:
    rows = (
        await session.execute(
            select(UserFeedback.agree, UserFeedback.will_trade, func.count(UserFeedback.id))
            .where(UserFeedback.signal_type == signal_type)
            .group_by(UserFeedback.agree, UserFeedback.will_trade)
        )
    ).all()
    agree_count = 0
    disagree_count = 0
    uncertain_count = 0
    will_trade_count = 0
    for agree, will_trade, count in rows:
        row_count = int(count)
        if agree == "agree":
            agree_count += row_count
        elif agree == "disagree":
            disagree_count += row_count
        elif agree == "uncertain":
            uncertain_count += row_count
        if will_trade == "will_trade":
            will_trade_count += row_count
    return FeedbackSummary(
        signal_type=signal_type,
        agree_count=agree_count,
        disagree_count=disagree_count,
        uncertain_count=uncertain_count,
        will_trade_count=will_trade_count,
    )


async def feedback_hint_for_signal(
    session: AsyncSession | None,
    *,
    signal_type: str,
    minimum_feedback: int = 3,
) -> FeedbackHint | None:
    if session is None:
        return None
    try:
        summary = await feedback_summary_by_signal_type(session, signal_type=signal_type)
    except Exception:
        await rollback_if_possible(session)
        return None
    total = summary.agree_count + summary.disagree_count + summary.uncertain_count
    if total < minimum_feedback or summary.disagree_count <= summary.agree_count:
        return None
    return FeedbackHint(
        signal_type=signal_type,
        hint=(
            f"历史反馈提示：你对 {signal_type} 类信号的不同意次数更多，"
            "建议人工复核后再放大仓位。"
        ),
        agree_count=summary.agree_count,
        disagree_count=summary.disagree_count,
    )
