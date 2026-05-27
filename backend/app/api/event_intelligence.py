from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.event_intelligence import EventIntelligenceAuditLog
from app.schemas.common import MAX_INGEST_SYMBOL_LENGTH
from app.schemas.event_intelligence import (
    EVENT_IMPACT_DIRECTION_PATTERN,
    EVENT_IMPACT_MECHANISM_PATTERN,
    EVENT_INTELLIGENCE_STATUS_PATTERN,
    EventIntelligenceAuditLogRead,
    EventIntelligenceDecisionCreate,
    EventIntelligenceDecisionResponse,
    EventIntelligenceEvalCaseRead,
    EventIntelligenceQualitySummary,
    EventIntelligenceSnapshot,
    EventIntelligenceSourceLookupRequest,
    EventIntelligenceSourceLookupResponse,
    EventImpactLinkRead,
    EventImpactLinkUpdate,
    EventImpactLinkUpdateResponse,
    EventIntelligenceRead,
    EventIntelligenceResolveResponse,
)
from app.services.event_intelligence import (
    apply_event_intelligence_decision,
    evaluate_event_intelligence_quality,
    enhance_news_event_impacts_with_semantics,
    resolve_news_event_impacts,
    summarize_event_intelligence_quality,
    update_event_impact_link,
)
from app.services.event_intelligence.eval_cases import EVENT_INTELLIGENCE_EVAL_CASES
from app.services.llm.types import LLMConfigurationError
from app.services.symbols import normalize_root_symbol

router = APIRouter(prefix="/api/event-intelligence", tags=["event-intelligence"])
EVENT_INTELLIGENCE_SNAPSHOT_CACHE_TTL_SECONDS = 12
EVENT_INTELLIGENCE_SNAPSHOT_CACHE_MAX_ENTRIES = 128

_EVENT_INTELLIGENCE_SNAPSHOT_CACHE: dict[
    tuple[object, ...],
    tuple[datetime, EventIntelligenceSnapshot],
] = {}


@router.get("", response_model=list[EventIntelligenceRead])
async def list_event_intelligence(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventIntelligenceItem]:
    statement = _event_intelligence_items_statement(
        symbol=symbol,
        region_id=region_id,
        mechanism=mechanism,
        status_filter=status_filter,
        limit=limit,
        before=before,
    )
    return list((await session.scalars(statement)).all())


@router.get("/impact-links", response_model=list[EventImpactLinkRead])
async def list_event_impact_links(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    direction: str | None = Query(default=None, pattern=EVENT_IMPACT_DIRECTION_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    before_impact_score: float | None = Query(default=None, ge=0, le=100),
    before_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventImpactLink]:
    statement = _event_impact_links_statement(
        symbol=symbol,
        region_id=region_id,
        mechanism=mechanism,
        direction=direction,
        status_filter=status_filter,
        limit=limit,
        before_impact_score=before_impact_score,
        before_confidence=before_confidence,
    )
    return list((await session.scalars(statement)).all())


@router.patch("/impact-links/{link_id}", response_model=EventImpactLinkUpdateResponse)
async def update_event_intelligence_impact_link(
    link_id: UUID,
    payload: EventImpactLinkUpdate,
    session: AsyncSession = Depends(get_db),
) -> EventImpactLinkUpdateResponse:
    patch = payload.model_dump(exclude_unset=True, exclude={"edited_by", "note"})
    try:
        event_item, link, audit_log = await update_event_impact_link(
            session,
            link_id,
            edited_by=payload.edited_by,
            note=payload.note,
            changes=patch,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Impact link scope already exists") from exc
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.refresh(event_item)
    await session.refresh(link)
    await session.refresh(audit_log)
    _clear_event_intelligence_snapshot_cache()
    return EventImpactLinkUpdateResponse(
        event=EventIntelligenceRead.model_validate(event_item),
        impact_link=EventImpactLinkRead.model_validate(link),
        audit_log=EventIntelligenceAuditLogRead.model_validate(audit_log),
    )


@router.get("/audit-logs", response_model=list[EventIntelligenceAuditLogRead])
async def list_event_intelligence_audit_logs(
    event_item_id: UUID | None = None,
    action: str | None = Query(default=None, min_length=1, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventIntelligenceAuditLog]:
    statement = _event_intelligence_audit_logs_statement(
        event_item_id=event_item_id,
        action=action,
        limit=limit,
    )
    return list((await session.scalars(statement)).all())


@router.get("/eval-cases", response_model=list[EventIntelligenceEvalCaseRead])
async def list_event_intelligence_eval_cases() -> list[dict]:
    return [case.to_dict() for case in EVENT_INTELLIGENCE_EVAL_CASES]


@router.get("/quality", response_model=EventIntelligenceQualitySummary)
async def list_event_intelligence_quality(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceQualitySummary:
    statement = _event_intelligence_items_statement(
        symbol=symbol,
        region_id=region_id,
        mechanism=mechanism,
        status_filter=status_filter,
        limit=limit,
    )

    items = list((await session.scalars(statement)).all())
    item_ids = [item.id for item in items]
    links_by_event_id: dict[UUID, list[EventImpactLink]] = {item.id: [] for item in items}
    if item_ids:
        links = list(
            (
                await session.scalars(
                    _event_impact_links_for_items_statement(item_ids=item_ids)
                )
            ).all()
        )
        for link in links:
            links_by_event_id.setdefault(link.event_item_id, []).append(link)

    reports = [
        evaluate_event_intelligence_quality(item, links_by_event_id.get(item.id, []))
        for item in items
    ]
    return summarize_event_intelligence_quality(reports)


@router.get("/snapshot", response_model=EventIntelligenceSnapshot)
async def get_event_intelligence_snapshot(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    limit: int = Query(default=100, ge=1, le=500),
    refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceSnapshot:
    cache_key = _event_intelligence_snapshot_cache_key(
        symbol=symbol,
        region_id=region_id,
        mechanism=mechanism,
        status_filter=status_filter,
        limit=limit,
    )
    if not refresh:
        cached = _event_intelligence_snapshot_cache_get(cache_key)
        if cached is not None:
            return cached

    snapshot = await _load_event_intelligence_snapshot(
        session,
        symbol=symbol,
        region_id=region_id,
        mechanism=mechanism,
        status_filter=status_filter,
        limit=limit,
    )
    _event_intelligence_snapshot_cache_set(cache_key, snapshot)
    return snapshot


async def _load_event_intelligence_snapshot(
    session: AsyncSession,
    *,
    symbol: str | None,
    region_id: str | None,
    mechanism: str | None,
    status_filter: str | None,
    limit: int,
) -> EventIntelligenceSnapshot:
    items = list(
        (
            await session.scalars(
                _event_intelligence_items_statement(
                    symbol=symbol,
                    region_id=region_id,
                    mechanism=mechanism,
                    status_filter=status_filter,
                    limit=limit,
                )
            )
        ).all()
    )
    item_ids = [item.id for item in items]
    links: list[EventImpactLink] = []
    if item_ids:
        links = list(
            (
                await session.scalars(
                    _event_impact_links_for_items_statement(item_ids=item_ids)
                )
            ).all()
        )
    return _event_intelligence_snapshot_response(items, links)


def _event_intelligence_snapshot_cache_key(
    *,
    symbol: str | None,
    region_id: str | None,
    mechanism: str | None,
    status_filter: str | None,
    limit: int,
) -> tuple[object, ...]:
    return (
        "snapshot",
        limit,
        normalize_root_symbol(symbol) if symbol is not None else None,
        region_id,
        mechanism,
        status_filter,
    )


def _event_intelligence_snapshot_cache_get(
    key: tuple[object, ...],
    *,
    now: datetime | None = None,
) -> EventIntelligenceSnapshot | None:
    cached = _EVENT_INTELLIGENCE_SNAPSHOT_CACHE.get(key)
    if cached is None:
        return None
    cached_at, snapshot = cached
    effective_now = now or datetime.now(timezone.utc)
    if (effective_now - cached_at).total_seconds() > EVENT_INTELLIGENCE_SNAPSHOT_CACHE_TTL_SECONDS:
        _EVENT_INTELLIGENCE_SNAPSHOT_CACHE.pop(key, None)
        return None
    return snapshot.model_copy(deep=True)


def _event_intelligence_snapshot_cache_set(
    key: tuple[object, ...],
    snapshot: EventIntelligenceSnapshot,
    *,
    now: datetime | None = None,
) -> EventIntelligenceSnapshot:
    if (
        len(_EVENT_INTELLIGENCE_SNAPSHOT_CACHE) >= EVENT_INTELLIGENCE_SNAPSHOT_CACHE_MAX_ENTRIES
        and key not in _EVENT_INTELLIGENCE_SNAPSHOT_CACHE
    ):
        oldest_key = min(
            _EVENT_INTELLIGENCE_SNAPSHOT_CACHE,
            key=lambda item: _EVENT_INTELLIGENCE_SNAPSHOT_CACHE[item][0],
        )
        _EVENT_INTELLIGENCE_SNAPSHOT_CACHE.pop(oldest_key, None)
    _EVENT_INTELLIGENCE_SNAPSHOT_CACHE[key] = (
        now or datetime.now(timezone.utc),
        snapshot.model_copy(deep=True),
    )
    return snapshot


def _clear_event_intelligence_snapshot_cache() -> None:
    _EVENT_INTELLIGENCE_SNAPSHOT_CACHE.clear()


@router.post("/source-lookup", response_model=EventIntelligenceSourceLookupResponse)
async def lookup_event_intelligence_by_source(
    payload: EventIntelligenceSourceLookupRequest,
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceSourceLookupResponse:
    items = list(
        (
            await session.scalars(
                _event_intelligence_source_lookup_statement(
                    source_type=payload.source_type,
                    source_ids=payload.source_ids,
                )
            )
        ).all()
    )
    item_ids = [item.id for item in items]
    links: list[EventImpactLink] = []
    if item_ids:
        links = list(
            (
                await session.scalars(
                    _event_impact_links_for_items_statement(item_ids=item_ids)
                )
            ).all()
        )
    return _event_intelligence_source_lookup_response(items, links)


def _event_intelligence_items_statement(
    *,
    symbol: str | None,
    region_id: str | None,
    mechanism: str | None,
    status_filter: str | None,
    limit: int,
    before: datetime | None = None,
):
    statement = select(EventIntelligenceItem).order_by(
        EventIntelligenceItem.event_timestamp.desc(),
        EventIntelligenceItem.impact_score.desc(),
        EventIntelligenceItem.id.desc(),
    )
    if symbol is not None:
        normalized_symbol = normalize_root_symbol(symbol)
        statement = (
            statement.where(EventIntelligenceItem.symbols.contains([normalized_symbol]))
            if normalized_symbol is not None
            else statement.where(false())
        )
    if region_id is not None:
        statement = statement.where(EventIntelligenceItem.regions.contains([region_id]))
    if mechanism is not None:
        statement = statement.where(EventIntelligenceItem.mechanisms.contains([mechanism]))
    if status_filter is not None:
        statement = statement.where(EventIntelligenceItem.status == status_filter)
    if before is not None:
        statement = statement.where(EventIntelligenceItem.event_timestamp < before)
    return statement.limit(limit)


def _event_intelligence_source_lookup_statement(
    *,
    source_type: str,
    source_ids: list[str],
):
    return (
        select(EventIntelligenceItem)
        .where(
            EventIntelligenceItem.source_type == source_type,
            EventIntelligenceItem.source_id.in_(source_ids),
        )
        .order_by(
            EventIntelligenceItem.event_timestamp.desc(),
            EventIntelligenceItem.impact_score.desc(),
            EventIntelligenceItem.id.desc(),
        )
    )


def _event_impact_links_statement(
    *,
    symbol: str | None,
    region_id: str | None,
    mechanism: str | None,
    direction: str | None,
    status_filter: str | None,
    limit: int,
    before_impact_score: float | None = None,
    before_confidence: float | None = None,
):
    statement = select(EventImpactLink).order_by(
        EventImpactLink.impact_score.desc(),
        EventImpactLink.confidence.desc(),
        EventImpactLink.id.desc(),
    )
    if symbol is not None:
        normalized_symbol = normalize_root_symbol(symbol)
        statement = (
            statement.where(EventImpactLink.symbol == normalized_symbol)
            if normalized_symbol is not None
            else statement.where(false())
        )
    if region_id is not None:
        statement = statement.where(EventImpactLink.region_id == region_id)
    if mechanism is not None:
        statement = statement.where(EventImpactLink.mechanism == mechanism)
    if direction is not None:
        statement = statement.where(EventImpactLink.direction == direction)
    if status_filter is not None:
        statement = statement.where(EventImpactLink.status == status_filter)
    if before_impact_score is not None:
        if before_confidence is not None:
            statement = statement.where(
                or_(
                    EventImpactLink.impact_score < before_impact_score,
                    and_(
                        EventImpactLink.impact_score == before_impact_score,
                        EventImpactLink.confidence < before_confidence,
                    ),
                )
            )
        else:
            statement = statement.where(EventImpactLink.impact_score < before_impact_score)
    return statement.limit(limit)


def _event_impact_links_for_items_statement(*, item_ids: list[UUID]):
    return (
        select(EventImpactLink)
        .where(EventImpactLink.event_item_id.in_(item_ids))
        .order_by(
            EventImpactLink.impact_score.desc(),
            EventImpactLink.confidence.desc(),
            EventImpactLink.id.desc(),
        )
    )


def _event_intelligence_audit_logs_statement(
    *,
    event_item_id: UUID | None,
    action: str | None,
    limit: int,
):
    statement = select(EventIntelligenceAuditLog).order_by(
        EventIntelligenceAuditLog.created_at.desc(),
        EventIntelligenceAuditLog.id.desc(),
    )
    if event_item_id is not None:
        statement = statement.where(EventIntelligenceAuditLog.event_item_id == event_item_id)
    if action is not None:
        statement = statement.where(EventIntelligenceAuditLog.action == action)
    return statement.limit(limit)


@router.post(
    "/from-news/{news_event_id}",
    response_model=EventIntelligenceResolveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_intelligence_from_news(
    news_event_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceResolveResponse:
    try:
        event_item, links, created = await resolve_news_event_impacts(session, news_event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="News event not found") from exc

    await session.commit()
    await session.refresh(event_item)
    for link in links:
        await session.refresh(link)
    _clear_event_intelligence_snapshot_cache()
    if not created:
        response.status_code = status.HTTP_200_OK
    return _resolve_response(event_item, links, created=created)


@router.post("/{event_id}/decision", response_model=EventIntelligenceDecisionResponse)
async def decide_event_intelligence(
    event_id: UUID,
    payload: EventIntelligenceDecisionCreate,
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceDecisionResponse:
    try:
        event_item, audit_log = await apply_event_intelligence_decision(
            session,
            event_id,
            **payload.model_dump(),
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail="Event intelligence item not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(event_item)
    await session.refresh(audit_log)
    _clear_event_intelligence_snapshot_cache()
    return EventIntelligenceDecisionResponse(
        event=EventIntelligenceRead.model_validate(event_item),
        audit_log=EventIntelligenceAuditLogRead.model_validate(audit_log),
    )


@router.post(
    "/from-news/{news_event_id}/semantic",
    response_model=EventIntelligenceResolveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enhance_event_intelligence_from_news_with_semantics(
    news_event_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceResolveResponse:
    try:
        event_item, links, created = await enhance_news_event_impacts_with_semantics(
            session,
            news_event_id,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail="News event not found") from exc
        raise HTTPException(status_code=502, detail="Semantic extraction failed") from exc
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(event_item)
    for link in links:
        await session.refresh(link)
    _clear_event_intelligence_snapshot_cache()
    if not created:
        response.status_code = status.HTTP_200_OK
    return _resolve_response(event_item, links, created=created)


@router.get("/{event_id}", response_model=EventIntelligenceResolveResponse)
async def get_event_intelligence(
    event_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> EventIntelligenceResolveResponse:
    event_item = await session.get(EventIntelligenceItem, event_id)
    if event_item is None:
        raise HTTPException(status_code=404, detail="Event intelligence item not found")
    links = list(
        (
            await session.scalars(
                select(EventImpactLink)
                .where(EventImpactLink.event_item_id == event_item.id)
                .order_by(
                    EventImpactLink.impact_score.desc(),
                    EventImpactLink.confidence.desc(),
                    EventImpactLink.id.desc(),
                )
            )
        ).all()
    )
    return _resolve_response(event_item, links, created=False)


def _resolve_response(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink],
    *,
    created: bool,
) -> EventIntelligenceResolveResponse:
    return EventIntelligenceResolveResponse(
        event=EventIntelligenceRead.model_validate(event_item),
        impact_links=[EventImpactLinkRead.model_validate(link) for link in links],
        created=created,
    )


def _event_intelligence_snapshot_response(
    items: list[EventIntelligenceItem],
    links: list[EventImpactLink],
) -> EventIntelligenceSnapshot:
    links_by_event_id: dict[UUID, list[EventImpactLink]] = {item.id: [] for item in items}
    for link in links:
        links_by_event_id.setdefault(link.event_item_id, []).append(link)

    reports = [
        evaluate_event_intelligence_quality(item, links_by_event_id.get(item.id, []))
        for item in items
    ]
    return EventIntelligenceSnapshot(
        items=[EventIntelligenceRead.model_validate(item) for item in items],
        impact_links=[EventImpactLinkRead.model_validate(link) for link in links],
        quality=summarize_event_intelligence_quality(reports),
    )


def _event_intelligence_source_lookup_response(
    items: list[EventIntelligenceItem],
    links: list[EventImpactLink],
) -> EventIntelligenceSourceLookupResponse:
    return EventIntelligenceSourceLookupResponse(
        items=[EventIntelligenceRead.model_validate(item) for item in items],
        impact_links=[EventImpactLinkRead.model_validate(link) for link in links],
    )
