from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
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
    EventImpactLinkRead,
    EventIntelligenceRead,
    EventIntelligenceResolveResponse,
)
from app.services.event_intelligence import (
    apply_event_intelligence_decision,
    evaluate_event_intelligence_quality,
    enhance_news_event_impacts_with_semantics,
    resolve_news_event_impacts,
    summarize_event_intelligence_quality,
)
from app.services.event_intelligence.eval_cases import EVENT_INTELLIGENCE_EVAL_CASES
from app.services.llm.types import LLMConfigurationError

router = APIRouter(prefix="/api/event-intelligence", tags=["event-intelligence"])


@router.get("", response_model=list[EventIntelligenceRead])
async def list_event_intelligence(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventIntelligenceItem]:
    statement = select(EventIntelligenceItem).order_by(
        EventIntelligenceItem.event_timestamp.desc(),
        EventIntelligenceItem.impact_score.desc(),
    )
    if symbol is not None:
        statement = statement.where(EventIntelligenceItem.symbols.contains([symbol.upper()]))
    if region_id is not None:
        statement = statement.where(EventIntelligenceItem.regions.contains([region_id]))
    if mechanism is not None:
        statement = statement.where(EventIntelligenceItem.mechanisms.contains([mechanism]))
    if status_filter is not None:
        statement = statement.where(EventIntelligenceItem.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


@router.get("/impact-links", response_model=list[EventImpactLinkRead])
async def list_event_impact_links(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    region_id: str | None = Query(default=None, min_length=1, max_length=80),
    mechanism: str | None = Query(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN),
    direction: str | None = Query(default=None, pattern=EVENT_IMPACT_DIRECTION_PATTERN),
    status_filter: str | None = Query(default=None, alias="status", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventImpactLink]:
    statement = select(EventImpactLink).order_by(
        EventImpactLink.impact_score.desc(),
        EventImpactLink.confidence.desc(),
    )
    if symbol is not None:
        statement = statement.where(EventImpactLink.symbol == symbol.upper())
    if region_id is not None:
        statement = statement.where(EventImpactLink.region_id == region_id)
    if mechanism is not None:
        statement = statement.where(EventImpactLink.mechanism == mechanism)
    if direction is not None:
        statement = statement.where(EventImpactLink.direction == direction)
    if status_filter is not None:
        statement = statement.where(EventImpactLink.status == status_filter)
    return list((await session.scalars(statement.limit(limit))).all())


@router.get("/audit-logs", response_model=list[EventIntelligenceAuditLogRead])
async def list_event_intelligence_audit_logs(
    event_item_id: UUID | None = None,
    action: str | None = Query(default=None, min_length=1, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[EventIntelligenceAuditLog]:
    statement = select(EventIntelligenceAuditLog).order_by(
        EventIntelligenceAuditLog.created_at.desc()
    )
    if event_item_id is not None:
        statement = statement.where(EventIntelligenceAuditLog.event_item_id == event_item_id)
    if action is not None:
        statement = statement.where(EventIntelligenceAuditLog.action == action)
    return list((await session.scalars(statement.limit(limit))).all())


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
    statement = select(EventIntelligenceItem).order_by(
        EventIntelligenceItem.event_timestamp.desc(),
        EventIntelligenceItem.impact_score.desc(),
    )
    if symbol is not None:
        statement = statement.where(EventIntelligenceItem.symbols.contains([symbol.upper()]))
    if region_id is not None:
        statement = statement.where(EventIntelligenceItem.regions.contains([region_id]))
    if mechanism is not None:
        statement = statement.where(EventIntelligenceItem.mechanisms.contains([mechanism]))
    if status_filter is not None:
        statement = statement.where(EventIntelligenceItem.status == status_filter)

    items = list((await session.scalars(statement.limit(limit))).all())
    item_ids = [item.id for item in items]
    links_by_event_id: dict[UUID, list[EventImpactLink]] = {item.id: [] for item in items}
    if item_ids:
        links = list(
            (
                await session.scalars(
                    select(EventImpactLink)
                    .where(EventImpactLink.event_item_id.in_(item_ids))
                    .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
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
                .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
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
