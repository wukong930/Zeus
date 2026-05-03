import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_events import NewsEvent
from app.services.vector_search.hybrid_search import VectorSearchResult, hybrid_search

TITLE_TOKEN_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class DedupDecision:
    duplicate: bool
    matched_event_id: UUID | None = None
    reason: str = "new"
    semantic_matches: list[VectorSearchResult] | None = None


def normalize_title(title: str) -> str:
    normalized = TITLE_TOKEN_RE.sub("", title.lower())
    return normalized.strip()


def news_dedup_hash(
    *,
    title: str,
    published_at: datetime,
    affected_symbols: list[str],
) -> str:
    day_bucket = _ensure_tz(published_at).date().isoformat()
    payload = "|".join(
        [
            day_bucket,
            normalize_title(title),
            ",".join(sorted(symbol.upper() for symbol in affected_symbols)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def find_title_duplicate(
    session: AsyncSession,
    *,
    dedup_hash: str,
) -> NewsEvent | None:
    return (
        await session.scalars(select(NewsEvent).where(NewsEvent.dedup_hash == dedup_hash).limit(1))
    ).first()


async def deduplicate_news_event(
    session: AsyncSession,
    *,
    title: str,
    published_at: datetime,
    affected_symbols: list[str],
    content_text: str,
    query_embedding: list[float] | None = None,
    semantic_threshold: float = 0.88,
) -> DedupDecision:
    dedup_hash = news_dedup_hash(
        title=title,
        published_at=published_at,
        affected_symbols=affected_symbols,
    )
    title_duplicate = await find_title_duplicate(session, dedup_hash=dedup_hash)
    if title_duplicate is not None:
        return DedupDecision(
            duplicate=True,
            matched_event_id=title_duplicate.id,
            reason="title_hash",
        )

    semantic_matches = await semantic_duplicate_candidates(
        session,
        content_text=content_text,
        published_at=published_at,
        query_embedding=query_embedding,
        limit=5,
    )
    strong_match = next(
        (match for match in semantic_matches if match.cosine_score >= semantic_threshold),
        None,
    )
    if strong_match is not None:
        return DedupDecision(
            duplicate=True,
            matched_event_id=strong_match.source_id,
            reason="semantic_similarity",
            semantic_matches=semantic_matches,
        )

    return DedupDecision(duplicate=False, semantic_matches=semantic_matches)


async def semantic_duplicate_candidates(
    session: AsyncSession,
    *,
    content_text: str,
    published_at: datetime,
    query_embedding: list[float] | None,
    limit: int = 5,
) -> list[VectorSearchResult]:
    if query_embedding is None:
        return []
    published_at = _ensure_tz(published_at)
    return await hybrid_search(
        session,
        query_text=content_text,
        query_embedding=query_embedding,
        chunk_type="news",
        date_from=published_at - timedelta(hours=24),
        date_to=published_at + timedelta(hours=24),
        limit=limit,
        half_life_days=1,
    )


def _ensure_tz(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
