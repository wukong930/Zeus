from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_review_queue import ChangeReviewQueue

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class ReviewRequiredError(RuntimeError):
    pass


async def enqueue_review(
    session: AsyncSession,
    *,
    source: str,
    target_table: str,
    target_key: str,
    proposed_change: dict[str, Any],
    reason: str | None = None,
) -> ChangeReviewQueue:
    existing = (
        await session.scalars(
            select(ChangeReviewQueue)
            .where(
                ChangeReviewQueue.source == source,
                ChangeReviewQueue.target_table == target_table,
                ChangeReviewQueue.target_key == target_key,
                ChangeReviewQueue.status == "pending",
            )
            .limit(1)
        )
    ).first()
    if existing is not None:
        return existing

    row = ChangeReviewQueue(
        source=source,
        target_table=target_table,
        target_key=target_key,
        proposed_change=proposed_change,
        status="pending",
        reason=reason,
    )
    session.add(row)
    await session.flush()
    return row


def review_required(target_table: str) -> Callable[[F], F]:
    def decorator(function: F) -> F:
        @wraps(function)
        async def wrapper(
            *args: Any,
            human_approved: bool = False,
            review_source: str = "system",
            target_key: str | None = None,
            proposed_change: dict[str, Any] | None = None,
            reason: str | None = None,
            **kwargs: Any,
        ) -> Any:
            if human_approved:
                return await function(*args, **kwargs)

            session = _find_session(args, kwargs)
            if session is None:
                raise ReviewRequiredError(f"{target_table} change requires an AsyncSession")

            key = target_key or _target_key_from_change(proposed_change) or function.__name__
            await enqueue_review(
                session,
                source=review_source,
                target_table=target_table,
                target_key=key,
                proposed_change=proposed_change or {"function": function.__name__},
                reason=reason or "Human approval is required before production write.",
            )
            raise ReviewRequiredError(f"{target_table} change queued for human review: {key}")

        return wrapper  # type: ignore[return-value]

    return decorator


def _find_session(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AsyncSession | None:
    session = kwargs.get("session")
    if _looks_like_session(session):
        return session
    for arg in args:
        if _looks_like_session(arg):
            return arg
    return None


def _looks_like_session(value: Any) -> bool:
    return isinstance(value, AsyncSession) or (
        hasattr(value, "add") and hasattr(value, "flush") and hasattr(value, "scalars")
    )


def _target_key_from_change(proposed_change: dict[str, Any] | None) -> str | None:
    if proposed_change is None:
        return None
    keys = [
        proposed_change.get("signal_type"),
        proposed_change.get("category"),
        proposed_change.get("regime"),
    ]
    if all(keys):
        return ":".join(str(key) for key in keys)
    return None
