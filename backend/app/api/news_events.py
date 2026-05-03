import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import ZeusEvent, iter_events
from app.models.news_events import NewsEvent
from app.schemas.common import NewsEventCreate, NewsEventRead
from app.services.news.event_publisher import record_and_publish_news_event
from app.services.vector_search.embedder import DeterministicHashEmbedder

router = APIRouter(prefix="/api/news-events", tags=["news-events"])


@router.get("", response_model=list[NewsEventRead])
async def list_news_events(
    source: str | None = None,
    symbol: str | None = None,
    event_type: str | None = None,
    min_severity: int | None = Query(default=None, ge=1, le=5),
    verification_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[NewsEvent]:
    statement = select(NewsEvent).order_by(NewsEvent.published_at.desc())
    if source is not None:
        statement = statement.where(NewsEvent.source == source)
    if symbol is not None:
        statement = statement.where(NewsEvent.affected_symbols.contains([symbol.upper()]))
    if event_type is not None:
        statement = statement.where(NewsEvent.event_type == event_type)
    if min_severity is not None:
        statement = statement.where(NewsEvent.severity >= min_severity)
    if verification_status is not None:
        statement = statement.where(NewsEvent.verification_status == verification_status)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=NewsEventRead, status_code=status.HTTP_201_CREATED)
async def create_news_event(
    payload: NewsEventCreate,
    session: AsyncSession = Depends(get_db),
) -> NewsEvent:
    content = "\n".join(
        part
        for part in (
            payload.title,
            payload.summary or "",
            payload.content_text or "",
        )
        if part
    )
    embedding = await DeterministicHashEmbedder().embed_text(content)
    result = await record_and_publish_news_event(session, payload, embedding=embedding)
    await session.commit()
    await session.refresh(result.row)
    return result.row


@router.get("/stream")
async def stream_news_events() -> StreamingResponse:
    return StreamingResponse(
        _news_event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{news_event_id}", response_model=NewsEventRead)
async def get_news_event(
    news_event_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> NewsEvent:
    row = await session.get(NewsEvent, news_event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="News event not found")
    return row


async def _news_event_stream():
    async for event in iter_events("news.event"):
        yield format_news_sse_event(event)


def format_news_sse_event(event: ZeusEvent) -> str:
    payload = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
    return f"id: {event.id}\nevent: {event.channel}\ndata: {payload}\n\n"
