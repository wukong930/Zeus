from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.learning_hypotheses import LearningHypothesis
from app.services.learning.reflection_agent import run_reflection_agent
from app.services.shadow.comparator import compare_shadow_run
from app.services.shadow.runner import create_shadow_run
from app.services.vector_search.eval import compare_vector_search_candidate, evaluate_vector_search
from app.services.vector_search.eval_seed import seed_vector_eval_cases

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/hypotheses")
async def list_learning_hypotheses(
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    statement = select(LearningHypothesis).order_by(LearningHypothesis.created_at.desc())
    if status_filter is not None:
        statement = statement.where(LearningHypothesis.status == status_filter)
    rows = (await session.scalars(statement.limit(limit))).all()
    return [learning_hypothesis_to_dict(row) for row in rows]


@router.post("/reflection/run", status_code=status.HTTP_202_ACCEPTED)
async def run_learning_reflection(
    lookback_days: int = Query(default=30, ge=14, le=90),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await run_reflection_agent(session, lookback_days=lookback_days)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await session.commit()
    return result.to_dict()


@router.post("/hypotheses/{hypothesis_id}/approve-shadow")
async def approve_hypothesis_for_shadow(
    hypothesis_id: UUID,
    reviewed_by: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await session.get(LearningHypothesis, hypothesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Learning hypothesis not found")
    if row.status not in {"proposed", "reviewed"}:
        raise HTTPException(status_code=409, detail=f"Hypothesis status is {row.status}")
    now = datetime.now(timezone.utc)
    shadow_run = await create_shadow_run(
        session,
        name=f"hypothesis-{str(row.id)[:8]}",
        algorithm_version="llm-reflection-shadow",
        config_diff={
            "source_hypothesis_id": str(row.id),
            "hypothesis": row.hypothesis,
            "proposed_change": row.proposed_change,
            "confidence": row.confidence,
            "evidence_strength": row.evidence_strength,
        },
        created_by=reviewed_by,
        notes="Created from approved learning hypothesis; no production parameters changed.",
        started_at=now,
        ended_at=now + timedelta(days=30),
    )
    row.status = "shadow_testing"
    await session.commit()
    return {
        "hypothesis": learning_hypothesis_to_dict(row),
        "shadow_run_id": str(shadow_run.id),
    }


@router.post("/hypotheses/{hypothesis_id}/reject")
async def reject_learning_hypothesis(
    hypothesis_id: UUID,
    reason: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await session.get(LearningHypothesis, hypothesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Learning hypothesis not found")
    row.status = "rejected"
    row.rejection_reason = reason or row.rejection_reason or "human_rejected"
    await session.commit()
    return learning_hypothesis_to_dict(row)


@router.post("/hypotheses/{hypothesis_id}/validate")
async def validate_learning_hypothesis(
    hypothesis_id: UUID,
    shadow_run_id: UUID,
    min_hit_rate_delta: float = Query(default=0.0, ge=-1.0, le=1.0),
    max_disagreement_rate: float = Query(default=0.35, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await session.get(LearningHypothesis, hypothesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Learning hypothesis not found")
    if row.status != "shadow_testing":
        raise HTTPException(status_code=409, detail=f"Hypothesis status is {row.status}")
    report = await compare_shadow_run(session, shadow_run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    hit_rate_delta = report.hit_rate_delta
    if hit_rate_delta is None:
        raise HTTPException(status_code=409, detail="Shadow run does not have resolved outcomes")
    if hit_rate_delta < min_hit_rate_delta or report.disagreement_rate > max_disagreement_rate:
        raise HTTPException(
            status_code=409,
            detail="Shadow report did not pass validation gates",
        )
    row.status = "validated"
    row.source_payload = {
        **(row.source_payload or {}),
        "validation": report.to_dict(),
    }
    await session.commit()
    return learning_hypothesis_to_dict(row)


@router.post("/hypotheses/{hypothesis_id}/apply")
async def apply_learning_hypothesis(
    hypothesis_id: UUID,
    approved_by: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await session.get(LearningHypothesis, hypothesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Learning hypothesis not found")
    if row.status != "validated":
        raise HTTPException(status_code=409, detail=f"Hypothesis status is {row.status}")
    row.status = "applied"
    row.source_payload = {
        **(row.source_payload or {}),
        "final_approval": {
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "note": "Status-only production adoption marker; parameter writes still require table-specific review guards.",
        },
    }
    await session.commit()
    return learning_hypothesis_to_dict(row)


@router.get("/vector-eval/report")
async def get_vector_eval_report(
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await evaluate_vector_search(session, limit=limit)
    return report.to_dict()


@router.get("/vector-eval/shadow-compare")
async def compare_vector_embedding_shadow(
    candidate_name: str = "candidate",
    limit: int = Query(default=10, ge=1, le=50),
    min_ndcg_delta: float = Query(default=0.0, ge=-1.0, le=1.0),
    min_recall_delta: float = Query(default=0.0, ge=-1.0, le=1.0),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    comparison = await compare_vector_search_candidate(
        session,
        candidate_name=candidate_name,
        limit=limit,
        min_ndcg_delta=min_ndcg_delta,
        min_recall_delta=min_recall_delta,
    )
    return comparison.to_dict()


@router.post("/vector-eval/seed", status_code=status.HTTP_201_CREATED)
async def seed_vector_eval_report(
    target_cases: int = Query(default=50, ge=1, le=200),
    reviewed_by: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await seed_vector_eval_cases(
        session,
        target_cases=target_cases,
        reviewed_by=reviewed_by,
    )
    await session.commit()
    return result.to_dict()


def learning_hypothesis_to_dict(row: LearningHypothesis) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "hypothesis": row.hypothesis,
        "supporting_evidence": row.supporting_evidence,
        "proposed_change": row.proposed_change,
        "confidence": row.confidence,
        "sample_size": row.sample_size,
        "counterevidence": row.counterevidence,
        "status": row.status,
        "evidence_strength": row.evidence_strength,
        "rejection_reason": row.rejection_reason,
        "source_payload": row.source_payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
