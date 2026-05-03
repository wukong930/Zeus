from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class VectorSearchResult:
    id: UUID
    chunk_type: str
    source_id: UUID | None
    content_text: str
    metadata: dict[str, Any]
    quality_status: str
    final_score: float
    cosine_score: float
    text_score: float
    time_decay: float
    created_at: datetime


def vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in embedding) + "]"


async def hybrid_search(
    session: AsyncSession,
    *,
    query_text: str,
    query_embedding: list[float] | None = None,
    chunk_type: str | None = None,
    sector: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 10,
    alpha: float = 0.6,
    beta: float = 0.3,
    gamma: float = 0.1,
    half_life_days: float = 30.0,
    ef_search: int = 40,
) -> list[VectorSearchResult]:
    filters = ["1 = 1"]
    params: dict[str, Any] = {
        "query_text": query_text,
        "limit": limit,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "half_life_days": max(1.0, half_life_days),
    }
    if chunk_type is not None:
        filters.append("chunk_type = :chunk_type")
        params["chunk_type"] = chunk_type
    if sector is not None:
        filters.append("metadata->>'sector' = :sector")
        params["sector"] = sector
    if date_from is not None:
        filters.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        filters.append("created_at <= :date_to")
        params["date_to"] = date_to

    if query_embedding is not None:
        params["query_embedding"] = vector_literal(query_embedding)
        cosine_expr = "COALESCE(1 - (embedding <=> CAST(:query_embedding AS vector)), 0)"
        ordering_hint = "embedding <=> CAST(:query_embedding AS vector),"
        await session.execute(text("SET LOCAL hnsw.ef_search = :ef_search"), {"ef_search": ef_search})
    else:
        cosine_expr = "0"
        ordering_hint = ""

    statement = text(
        f"""
        WITH scored AS (
            SELECT
                id,
                chunk_type,
                source_id,
                content_text,
                metadata,
                quality_status,
                created_at,
                {cosine_expr} AS cosine_score,
                ts_rank_cd(
                    to_tsvector('simple', content_text),
                    plainto_tsquery('simple', :query_text)
                ) AS text_score,
                exp(
                    -GREATEST(EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0, 0)
                    / :half_life_days
                ) AS time_decay
            FROM vector_chunks
            WHERE {" AND ".join(filters)}
            ORDER BY {ordering_hint} created_at DESC
            LIMIT :limit
        )
        SELECT
            *,
            (:alpha * cosine_score + :beta * text_score + :gamma * time_decay)
            * CASE quality_status
                WHEN 'validated' THEN 1.2
                WHEN 'human_reviewed' THEN 1.0
                ELSE 0.5
              END AS final_score
        FROM scored
        ORDER BY final_score DESC, created_at DESC
        LIMIT :limit
        """
    )
    rows = (await session.execute(statement, params)).mappings().all()
    return [
        VectorSearchResult(
            id=row["id"],
            chunk_type=row["chunk_type"],
            source_id=row["source_id"],
            content_text=row["content_text"],
            metadata=dict(row["metadata"] or {}),
            quality_status=row["quality_status"],
            final_score=float(row["final_score"] or 0),
            cosine_score=float(row["cosine_score"] or 0),
            text_score=float(row["text_score"] or 0),
            time_decay=float(row["time_decay"] or 0),
            created_at=row["created_at"],
        )
        for row in rows
    ]
