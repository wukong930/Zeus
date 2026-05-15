from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ZeusEvent, publish
from app.models.news_events import NewsEvent
from app.models.vector_chunks import VectorChunk
from app.services.event_intelligence import resolve_news_event_impacts
from app.services.news.dedup import news_dedup_hash
from app.services.news.extractor import StructuredNewsEvent
from app.services.news.quality import (
    is_evaluable_news_event,
    requires_manual_confirmation,
    verification_status_for,
)
from app.services.translation import apply_news_event_translation
from app.services.vector_search.embedder import EmbeddingResult


@dataclass(frozen=True)
class NewsEventWriteResult:
    row: NewsEvent
    created: bool
    should_publish: bool
    published_event: ZeusEvent | None = None


async def record_and_publish_news_event(
    session: AsyncSession,
    payload: StructuredNewsEvent | BaseModel | dict[str, Any],
    *,
    embedding: EmbeddingResult | None = None,
    publisher=publish,
) -> NewsEventWriteResult:
    row, created, should_publish = await upsert_news_event(session, payload)
    await resolve_news_event_impacts(session, row.id)
    if created:
        store_vector_chunk(session, row, embedding=embedding)

    event = None
    if should_publish:
        event = await publisher(
            "news.event",
            news_event_bus_payload(row),
            source="news-pipeline",
            session=session,
        )
    return NewsEventWriteResult(
        row=row,
        created=created,
        should_publish=should_publish,
        published_event=event,
    )


async def upsert_news_event(
    session: AsyncSession,
    payload: StructuredNewsEvent | BaseModel | dict[str, Any],
) -> tuple[NewsEvent, bool, bool]:
    data = normalize_news_payload(payload)
    existing = (
        await session.scalars(
            select(NewsEvent).where(NewsEvent.dedup_hash == data["dedup_hash"]).limit(1)
        )
    ).first()
    if existing is not None:
        was_evaluable = event_row_is_evaluable(existing)
        merge_duplicate_event(existing, data)
        await session.flush()
        return existing, False, event_row_is_evaluable(existing) and not was_evaluable

    row = NewsEvent(**data)
    session.add(row)
    await session.flush()
    return row, True, event_row_is_evaluable(row)


def normalize_news_payload(payload: StructuredNewsEvent | BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, StructuredNewsEvent):
        data = payload.with_dedup_hash().model_dump()
    elif isinstance(payload, BaseModel):
        data = payload.model_dump()
    else:
        data = dict(payload)

    affected_symbols = sorted(
        {str(symbol).strip().upper() for symbol in data.get("affected_symbols", []) if str(symbol).strip()}
    )
    published_at = _ensure_tz(data["published_at"])
    source_count = max(1, int(data.get("source_count") or 1))
    verification_status = data.get("verification_status") or verification_status_for(source_count)
    severity = int(data["severity"])
    extraction_payload = dict(data.get("extraction_payload") or {})
    sources = extraction_payload.get("sources")
    if not isinstance(sources, list):
        sources = []
    source = str(data["source"])
    if source not in sources:
        sources.append(source)
    extraction_payload["sources"] = sources

    row_data = {
        "source": source,
        "raw_url": data.get("raw_url"),
        "title": str(data["title"]),
        "summary": str(data.get("summary") or data["title"]),
        "content_text": data.get("content_text"),
        "published_at": published_at,
        "event_type": str(data["event_type"]),
        "affected_symbols": affected_symbols,
        "direction": str(data["direction"]),
        "severity": severity,
        "time_horizon": str(data["time_horizon"]),
        "llm_confidence": float(data["llm_confidence"]),
        "source_count": source_count,
        "verification_status": verification_status,
        "requires_manual_confirmation": requires_manual_confirmation(
            severity=severity,
            source_count=source_count,
            verification_status=verification_status,
        ),
        "dedup_hash": data.get("dedup_hash")
        or news_dedup_hash(
            title=str(data["title"]),
            published_at=published_at,
            affected_symbols=affected_symbols,
        ),
        "extraction_payload": extraction_payload,
    }
    for key in (
        "title_original",
        "summary_original",
        "title_zh",
        "summary_zh",
        "source_language",
        "translation_status",
        "translation_model",
        "translation_prompt_version",
        "translation_glossary_version",
        "translated_at",
    ):
        if key in data:
            row_data[key] = data[key]
    return apply_news_event_translation(row_data)


def merge_duplicate_event(row: NewsEvent, data: dict[str, Any]) -> None:
    payload = dict(row.extraction_payload or {})
    sources = payload.get("sources")
    if not isinstance(sources, list):
        sources = [row.source]
    if data["source"] not in sources:
        sources.append(data["source"])
    payload["sources"] = sources
    row.extraction_payload = {**payload, "last_duplicate": jsonable_news_payload(data)}
    row.source_count = max(int(row.source_count or 1), len(sources), int(data.get("source_count") or 1))
    row.verification_status = verification_status_for(
        row.source_count,
        manually_confirmed=row.verification_status == "manual_confirmed",
    )
    row.requires_manual_confirmation = requires_manual_confirmation(
        severity=row.severity,
        source_count=row.source_count,
        verification_status=row.verification_status,
    )
    if not row.raw_url and data.get("raw_url"):
        row.raw_url = data["raw_url"]
    row.updated_at = datetime.now(timezone.utc)


def event_row_is_evaluable(row: NewsEvent) -> bool:
    return (
        is_evaluable_news_event(
            severity=row.severity,
            source_count=row.source_count,
            verification_status=row.verification_status,
        )
        and not row.requires_manual_confirmation
    )


def store_vector_chunk(
    session: AsyncSession,
    row: NewsEvent,
    *,
    embedding: EmbeddingResult | None,
) -> VectorChunk:
    content = "\n".join(
        part
        for part in (
            row.title,
            row.summary,
            row.title_zh or "",
            row.summary_zh or "",
            row.content_text or "",
        )
        if part
    )
    chunk = VectorChunk(
        chunk_type="news",
        source_id=row.id,
        content_text=content,
        embedding=embedding.embedding if embedding is not None else None,
        embedding_model=embedding.embedding_model if embedding is not None else None,
        metadata_json={
            "source": row.source,
            "raw_url": row.raw_url,
            "event_type": row.event_type,
            "affected_symbols": row.affected_symbols,
            "direction": row.direction,
            "severity": row.severity,
            "source_language": row.source_language,
            "translation_status": row.translation_status,
            "published_at": row.published_at.isoformat(),
            "sector": infer_category_from_symbols(row.affected_symbols),
        },
        quality_status=(
            "human_reviewed" if row.verification_status == "manual_confirmed" else "unverified"
        ),
    )
    session.add(chunk)
    return chunk


def news_event_bus_payload(row: NewsEvent) -> dict[str, Any]:
    event_payload = news_event_payload(row)
    return {
        "news_event": event_payload,
        "contexts": [
            news_trigger_context(row, symbol, event_payload)
            for symbol in row.affected_symbols
        ],
    }


def news_event_payload(row: NewsEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source": row.source,
        "raw_url": row.raw_url,
        "title": row.title,
        "summary": row.summary,
        "title_original": row.title_original,
        "summary_original": row.summary_original,
        "title_zh": row.title_zh,
        "summary_zh": row.summary_zh,
        "source_language": row.source_language,
        "translation_status": row.translation_status,
        "translation_model": row.translation_model,
        "translation_prompt_version": row.translation_prompt_version,
        "translation_glossary_version": row.translation_glossary_version,
        "translated_at": row.translated_at.isoformat() if row.translated_at is not None else None,
        "published_at": row.published_at.isoformat(),
        "event_type": row.event_type,
        "affected_symbols": row.affected_symbols,
        "direction": row.direction,
        "severity": row.severity,
        "time_horizon": row.time_horizon,
        "llm_confidence": row.llm_confidence,
        "source_count": row.source_count,
        "verification_status": row.verification_status,
        "requires_manual_confirmation": row.requires_manual_confirmation,
    }


def news_trigger_context(
    row: NewsEvent,
    symbol: str,
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "symbol1": symbol,
        "category": infer_category_from_symbol(symbol),
        "timestamp": row.published_at.isoformat(),
        "regime": "news",
        "news_events": [event_payload or news_event_payload(row)],
    }


def infer_category_from_symbols(symbols: list[str]) -> str:
    if not symbols:
        return "unknown"
    categories = [infer_category_from_symbol(symbol) for symbol in symbols]
    for category in categories:
        if category != "unknown":
            return category
    return "unknown"


def infer_category_from_symbol(symbol: str) -> str:
    root = "".join(char for char in symbol.upper() if char.isalpha())
    if root in {"RB", "HC", "I", "J", "JM", "SF", "SM"}:
        return "ferrous"
    if root in {"RU", "NR", "BR"}:
        return "rubber"
    if root in {"SC", "FU", "TA", "EG", "MA", "PP", "L", "V"}:
        return "energy"
    if root in {"CU", "AL", "ZN", "NI", "SN", "PB"}:
        return "nonferrous"
    if root in {"M", "Y", "P", "C", "A", "CF", "SR"}:
        return "agriculture"
    return "unknown"


def _ensure_tz(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def jsonable_news_payload(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable_news_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable_news_payload(item) for item in value]
    return value
