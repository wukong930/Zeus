from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vector_chunks import VectorChunk
from app.models.vector_eval_set import VectorEvalCase

SEED_QUERY_TEMPLATES: tuple[str, ...] = (
    "{topic} upstream driver",
    "{topic} downstream impact",
    "{topic} cost support",
    "{topic} inventory pressure",
    "{topic} policy shock",
    "{topic} supply disruption",
    "{topic} demand weakness",
    "{topic} regime change",
    "{topic} futures spread",
    "{topic} risk evidence",
)


@dataclass(frozen=True)
class VectorEvalSeedResult:
    available_chunks: int
    existing_cases: int
    created: int
    target_cases: int

    def to_dict(self) -> dict:
        return asdict(self)


async def seed_vector_eval_cases(
    session: AsyncSession,
    *,
    target_cases: int = 50,
    reviewed_by: str | None = None,
) -> VectorEvalSeedResult:
    chunks = list(
        (
            await session.scalars(
                select(VectorChunk)
                .where(VectorChunk.quality_status.in_(("human_reviewed", "validated", "unverified")))
                .order_by(VectorChunk.created_at.asc())
                .limit(max(target_cases, 1))
            )
        ).all()
    )
    existing = list((await session.scalars(select(VectorEvalCase))).all())
    existing_queries = {row.query_text for row in existing}
    if not chunks:
        return VectorEvalSeedResult(
            available_chunks=0,
            existing_cases=len(existing),
            created=0,
            target_cases=target_cases,
        )

    created = 0
    for index in range(target_cases):
        chunk = chunks[index % len(chunks)]
        topic = _topic_for_chunk(chunk)
        query = SEED_QUERY_TEMPLATES[index % len(SEED_QUERY_TEMPLATES)].format(topic=topic)
        query = f"{query} #{index + 1:02d}"
        if query in existing_queries:
            continue
        session.add(
            VectorEvalCase(
                query_text=query,
                relevant_chunk_ids=[str(chunk.id)],
                tags=["phase9_seed", chunk.chunk_type],
                status="active",
                reviewed_by=reviewed_by,
            )
        )
        existing_queries.add(query)
        created += 1
    await session.flush()
    return VectorEvalSeedResult(
        available_chunks=len(chunks),
        existing_cases=len(existing),
        created=created,
        target_cases=target_cases,
    )


def _topic_for_chunk(chunk: VectorChunk) -> str:
    metadata = chunk.metadata_json or {}
    for key in ("symbol", "sector", "event_type", "source"):
        value = metadata.get(key)
        if value:
            return str(value).replace("_", " ")
    words = chunk.content_text.split()
    return " ".join(words[:4]) if words else chunk.chunk_type
