import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import ZeusEvent, iter_events
from app.models.alert import Alert
from app.schemas.common import AlertCreate, AlertRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    status_filter: str | None = Query(default=None, max_length=20),
    category: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Alert]:
    statement = select(Alert).order_by(Alert.triggered_at.desc())
    if status_filter is not None:
        statement = statement.where(Alert.status == status_filter)
    else:
        statement = statement.where(Alert.status != "suppressed")
    if category is not None:
        statement = statement.where(Alert.category == category)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate, session: AsyncSession = Depends(get_db)) -> Alert:
    row = Alert(**payload.model_dump(exclude_none=True))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/stream")
async def stream_alerts() -> StreamingResponse:
    return StreamingResponse(
        _alert_event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(alert_id: UUID, session: AsyncSession = Depends(get_db)) -> Alert:
    row = await session.get(Alert, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return row


async def _alert_event_stream():
    async for event in iter_events("alert.created"):
        yield format_sse_event(event)


def format_sse_event(event: ZeusEvent) -> str:
    payload = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
    return f"id: {event.id}\nevent: {event.channel}\ndata: {payload}\n\n"
