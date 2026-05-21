import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import ZeusEvent, iter_events
from app.models.alert import Alert
from app.schemas.common import AlertCreate, AlertRead
from app.services.translation import apply_alert_translation

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
ALERT_SEVERITY_LIST_PATTERN = (
    "^(low|medium|high|critical)(,(low|medium|high|critical))*$"
)


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    status_filter: str | None = Query(default=None, max_length=20),
    category: str | None = Query(default=None, max_length=20),
    severity: str | None = Query(default=None, pattern=ALERT_SEVERITY_LIST_PATTERN),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    human_action_required: bool | None = None,
    adversarial_passed: bool | None = None,
    include_expired: bool = False,
    q: str | None = Query(default=None, min_length=1, max_length=120),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[Alert]:
    statement = _alerts_statement(
        status_filter=status_filter,
        category=category,
        severity=severity,
        symbol=symbol,
        human_action_required=human_action_required,
        adversarial_passed=adversarial_passed,
        include_expired=include_expired,
        as_of=datetime.now(UTC),
        q=q,
        before=before,
        limit=limit,
    )
    return list((await session.scalars(statement)).all())


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate, session: AsyncSession = Depends(get_db)) -> Alert:
    data = payload.model_dump(exclude_none=True)
    row = Alert(**apply_alert_translation(data))
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


def _alerts_statement(
    *,
    status_filter: str | None,
    category: str | None,
    severity: str | None,
    symbol: str | None,
    human_action_required: bool | None,
    adversarial_passed: bool | None,
    q: str | None,
    limit: int,
    before: datetime | None = None,
    include_expired: bool = False,
    as_of: datetime | None = None,
):
    statement = select(Alert).order_by(Alert.triggered_at.desc(), Alert.id.desc())
    if status_filter is not None:
        statement = statement.where(Alert.status == status_filter)
    else:
        statement = statement.where(Alert.status != "suppressed")
    if not include_expired:
        effective_as_of = as_of or datetime.now(UTC)
        statement = statement.where(or_(Alert.expires_at.is_(None), Alert.expires_at > effective_as_of))
    if category is not None:
        statement = statement.where(Alert.category == category)
    if severity is not None:
        statement = statement.where(Alert.severity.in_(severity.split(",")))
    if symbol is not None:
        statement = statement.where(Alert.related_assets.contains([symbol.upper()]))
    if human_action_required is not None:
        statement = statement.where(Alert.human_action_required.is_(human_action_required))
    if adversarial_passed is not None:
        statement = statement.where(Alert.adversarial_passed.is_(adversarial_passed))
    if before is not None:
        statement = statement.where(Alert.triggered_at < before)
    if q is not None:
        query_text = q.strip()
        if query_text:
            query_symbol = query_text.upper()
            if len(query_symbol) <= 2 and query_symbol.isascii() and query_symbol.isalnum():
                statement = statement.where(Alert.related_assets.contains([query_symbol]))
            else:
                like_pattern = f"%{query_text}%"
                statement = statement.where(
                    or_(
                        Alert.title.ilike(like_pattern),
                        Alert.summary.ilike(like_pattern),
                        Alert.title_zh.ilike(like_pattern),
                        Alert.summary_zh.ilike(like_pattern),
                        Alert.one_liner.ilike(like_pattern),
                        Alert.related_assets.contains([query_symbol]),
                    )
                )
    return statement.limit(limit)
