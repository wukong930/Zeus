from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue
from app.models.user_feedback import UserFeedback
from app.services.governance.review_queue import enqueue_review


@dataclass(frozen=True)
class FeedbackReport:
    total_feedback: int
    by_signal_type: dict[str, dict[str, int]]
    suggestions: list[str]


async def generate_feedback_report(session: AsyncSession) -> FeedbackReport:
    rows = (
        await session.execute(
            select(
                UserFeedback.signal_type,
                UserFeedback.agree,
                UserFeedback.will_trade,
                func.count(UserFeedback.id),
            ).group_by(UserFeedback.signal_type, UserFeedback.agree, UserFeedback.will_trade)
        )
    ).all()
    grouped: dict[str, dict[str, int]] = {}
    total_feedback = 0
    for signal_type, agree, will_trade, count in rows:
        row_count = int(count)
        total_feedback += row_count
        key = signal_type or "unknown"
        bucket = grouped.setdefault(
            key,
            {"agree": 0, "disagree": 0, "uncertain": 0, "will_trade": 0},
        )
        bucket[agree] = bucket.get(agree, 0) + row_count
        if will_trade == "will_trade":
            bucket["will_trade"] += row_count

    suggestions = [
        f"{signal_type}: review disagreement pattern"
        for signal_type, stats in grouped.items()
        if stats.get("disagree", 0) >= 3 and stats.get("disagree", 0) > stats.get("agree", 0)
    ]
    return FeedbackReport(
        total_feedback=total_feedback,
        by_signal_type=grouped,
        suggestions=suggestions,
    )


async def enqueue_feedback_review_suggestions(session: AsyncSession) -> list[ChangeReviewQueue]:
    report = await generate_feedback_report(session)
    queued: list[ChangeReviewQueue] = []
    for signal_type, stats in report.by_signal_type.items():
        if stats.get("disagree", 0) < 3 or stats.get("disagree", 0) <= stats.get("agree", 0):
            continue
        queued.append(
            await enqueue_review(
                session,
                source="feedback",
                target_table="signal_calibration",
                target_key=f"feedback:{signal_type}",
                proposed_change={
                    "signal_type": signal_type,
                    "suggestion": "review_feedback_pattern",
                    "stats": stats,
                },
                reason="User feedback disagreement pattern requires human review before any rule change.",
            )
        )
    return queued
