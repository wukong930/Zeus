from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert_agent import HumanDecision
from app.schemas.common import HumanDecisionCreate, HumanDecisionRead
from app.services.alert_agent.human_decision import record_human_decision

router = APIRouter(prefix="/api/arbitration", tags=["arbitration"])


@router.get("/decisions", response_model=list[HumanDecisionRead])
async def list_human_decisions(
    alert_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[HumanDecision]:
    statement = select(HumanDecision).order_by(HumanDecision.created_at.desc())
    if alert_id is not None:
        statement = statement.where(HumanDecision.alert_id == alert_id)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("/decisions", response_model=HumanDecisionRead)
async def create_human_decision(
    payload: HumanDecisionCreate,
    session: AsyncSession = Depends(get_db),
) -> HumanDecision:
    if payload.alert_id is None and payload.signal_track_id is None:
        raise HTTPException(status_code=400, detail="alert_id or signal_track_id is required")
    row = await record_human_decision(session, **payload.model_dump())
    await session.commit()
    await session.refresh(row)
    return row
