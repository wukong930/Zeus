from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.recommendation import Recommendation
from app.models.user_feedback import UserFeedback
from app.schemas.common import UserFeedbackCreate, UserFeedbackRead
from app.services.learning.user_feedback import record_user_feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.get("", response_model=list[UserFeedbackRead])
async def list_feedback(
    alert_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[UserFeedback]:
    statement = select(UserFeedback).order_by(UserFeedback.recorded_at.desc())
    if alert_id is not None:
        statement = statement.where(UserFeedback.alert_id == alert_id)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=UserFeedbackRead)
async def create_feedback(
    payload: UserFeedbackCreate,
    session: AsyncSession = Depends(get_db),
) -> UserFeedback:
    await require_feedback_targets(session, payload)
    row = await record_user_feedback(
        session,
        alert_id=payload.alert_id,
        recommendation_id=payload.recommendation_id,
        agree=payload.agree,
        disagreement_reason=payload.disagreement_reason,
        will_trade=payload.will_trade,
        metadata=payload.metadata,
    )
    await session.commit()
    await session.refresh(row)
    return row


async def require_feedback_targets(
    session: AsyncSession,
    payload: UserFeedbackCreate,
) -> None:
    if payload.alert_id is None and payload.recommendation_id is None:
        raise HTTPException(status_code=400, detail="alert_id or recommendation_id is required")
    if payload.alert_id is not None and await session.get(Alert, payload.alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if (
        payload.recommendation_id is not None
        and await session.get(Recommendation, payload.recommendation_id) is None
    ):
        raise HTTPException(status_code=404, detail="Recommendation not found")
