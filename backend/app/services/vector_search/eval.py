from dataclasses import asdict, dataclass
from math import log2
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vector_eval_set import VectorEvalCase
from app.services.vector_search.hybrid_search import VectorSearchResult, hybrid_search


@dataclass(frozen=True)
class VectorEvalCaseResult:
    case_id: str
    query_text: str
    relevant_total: int
    retrieved: int
    hits: int
    ndcg_at_10: float
    recall_at_10: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VectorEvalReport:
    cases: int
    mean_ndcg_at_10: float
    mean_recall_at_10: float
    results: list[VectorEvalCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "mean_ndcg_at_10": self.mean_ndcg_at_10,
            "mean_recall_at_10": self.mean_recall_at_10,
            "results": [item.to_dict() for item in self.results],
        }


async def evaluate_vector_search(
    session: AsyncSession,
    *,
    limit: int = 10,
    searcher=hybrid_search,
) -> VectorEvalReport:
    cases = (
        await session.scalars(
            select(VectorEvalCase)
            .where(VectorEvalCase.status == "active")
            .order_by(VectorEvalCase.created_at.asc())
        )
    ).all()
    results: list[VectorEvalCaseResult] = []
    for case in cases:
        retrieved = await searcher(
            session,
            query_text=case.query_text,
            limit=limit,
        )
        results.append(evaluate_single_case(case, retrieved, limit=limit))
    return summarize_vector_eval(results)


def evaluate_single_case(
    case: VectorEvalCase,
    retrieved: list[VectorSearchResult],
    *,
    limit: int = 10,
) -> VectorEvalCaseResult:
    relevant = {UUID(str(item)) for item in case.relevant_chunk_ids}
    retrieved_ids = [row.id for row in retrieved[:limit]]
    hits = sum(1 for item in retrieved_ids if item in relevant)
    return VectorEvalCaseResult(
        case_id=str(case.id),
        query_text=case.query_text,
        relevant_total=len(relevant),
        retrieved=len(retrieved_ids),
        hits=hits,
        ndcg_at_10=round(ndcg_at_k(retrieved_ids, relevant, k=limit), 6),
        recall_at_10=round(hits / len(relevant), 6) if relevant else 0.0,
    )


def summarize_vector_eval(results: list[VectorEvalCaseResult]) -> VectorEvalReport:
    if not results:
        return VectorEvalReport(
            cases=0,
            mean_ndcg_at_10=0.0,
            mean_recall_at_10=0.0,
            results=[],
        )
    return VectorEvalReport(
        cases=len(results),
        mean_ndcg_at_10=round(
            sum(item.ndcg_at_10 for item in results) / len(results),
            6,
        ),
        mean_recall_at_10=round(
            sum(item.recall_at_10 for item in results) / len(results),
            6,
        ),
        results=results,
    )


def ndcg_at_k(retrieved_ids: list[UUID], relevant_ids: set[UUID], *, k: int = 10) -> float:
    if not relevant_ids:
        return 0.0
    dcg = 0.0
    for index, chunk_id in enumerate(retrieved_ids[:k], start=1):
        if chunk_id in relevant_ids:
            dcg += 1 / log2(index + 1)
    ideal_hits = min(len(relevant_ids), k)
    ideal = sum(1 / log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0
