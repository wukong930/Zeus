from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.models.news_events import NewsEvent
from app.services.news.dedup import deduplicate_news_event
from app.services.news.event_publisher import record_and_publish_news_event
from app.services.news.extractor import StructuredNewsEvent, extract_news_event
from app.services.news.types import RawNewsItem
from app.services.vector_search.embedder import DeterministicHashEmbedder


@dataclass(frozen=True)
class NewsIngestResult:
    collected: int
    recorded: int
    duplicates: int
    published: int


async def ingest_news_items(
    session: AsyncSession,
    raw_items: Iterable[RawNewsItem],
    *,
    publisher=publish,
) -> NewsIngestResult:
    embedder = DeterministicHashEmbedder()
    collected = 0
    recorded = 0
    duplicates = 0
    published = 0

    for item in raw_items:
        collected += 1
        extracted = await extract_news_event(item)
        content = news_event_text(extracted)
        embedding = await embedder.embed_text(content)
        decision = await deduplicate_news_event(
            session,
            title=extracted.title,
            published_at=extracted.published_at,
            affected_symbols=extracted.affected_symbols,
            content_text=content,
            query_embedding=embedding.embedding,
        )
        if decision.duplicate:
            duplicates += 1
            extracted = await align_duplicate_hash(session, extracted, decision.matched_event_id)

        result = await record_and_publish_news_event(
            session,
            extracted,
            embedding=embedding,
            publisher=publisher,
        )
        if result.created:
            recorded += 1
        if result.published_event is not None:
            published += 1

    return NewsIngestResult(
        collected=collected,
        recorded=recorded,
        duplicates=duplicates,
        published=published,
    )


def news_event_text(event: StructuredNewsEvent) -> str:
    return "\n".join(
        part
        for part in (
            event.title,
            event.summary,
            event.content_text or "",
        )
        if part
    )


async def align_duplicate_hash(
    session: AsyncSession,
    event: StructuredNewsEvent,
    matched_event_id,
) -> StructuredNewsEvent:
    if matched_event_id is None:
        return event
    existing = await session.get(NewsEvent, matched_event_id)
    if existing is None:
        return event
    return event.model_copy(update={"dedup_hash": existing.dedup_hash})
