from dataclasses import dataclass

from sqlalchemy import select
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
    rows = (await session.scalars(select(UserFeedback))).all()
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row.signal_type or "unknown"
        bucket = grouped.setdefault(
            key,
            {"agree": 0, "disagree": 0, "uncertain": 0, "will_trade": 0},
        )
        bucket[row.agree] = bucket.get(row.agree, 0) + 1
        if row.will_trade == "will_trade":
            bucket["will_trade"] += 1

    suggestions = [
        f"{signal_type}: review disagreement pattern"
        for signal_type, stats in grouped.items()
        if stats.get("disagree", 0) >= 3 and stats.get("disagree", 0) > stats.get("agree", 0)
    ]
    return FeedbackReport(
        total_feedback=len(rows),
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
