import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drift_metrics import DriftMetric
from app.models.learning_hypotheses import LearningHypothesis
from app.models.recommendation import Recommendation
from app.models.signal import SignalTrack
from app.models.user_feedback import UserFeedback
from app.models.vector_chunks import VectorChunk
from app.services.governance.review_queue import enqueue_review
from app.services.llm.registry import complete_with_llm_controls
from app.services.llm.types import LLMCompletionOptions, LLMCompletionResult, LLMMessage

ReflectionCompleter = Callable[..., Awaitable[LLMCompletionResult]]

WEAK_EVIDENCE_MIN_SAMPLES = 30
BANNED_AUTOMATION_TERMS = (
    "立即",
    "自动",
    "无需审核",
    "直接修改",
    "auto-apply",
    "without review",
    "immediately apply",
    "directly modify",
)


class LearningHypothesisCandidate(BaseModel):
    hypothesis: str = Field(min_length=8)
    supporting_evidence: list[str] = Field(min_length=1)
    proposed_change: str | None = None
    confidence: float = Field(ge=0, le=1)
    counterevidence_considered: list[str] = Field(min_length=0)
    sample_size: int = Field(ge=0)


@dataclass(frozen=True)
class ReflectionInputSnapshot:
    period_start: datetime
    period_end: datetime
    signals: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    feedback: list[dict[str, Any]]
    drift: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "signals": self.signals,
            "recommendations": self.recommendations,
            "feedback": self.feedback,
            "drift": self.drift,
        }


@dataclass(frozen=True)
class ReflectionAgentResult:
    generated: int
    proposed: int
    rejected: int
    weak_evidence: int
    review_queued: int
    hypothesis_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def run_reflection_agent(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    completer: ReflectionCompleter = complete_with_llm_controls,
) -> ReflectionAgentResult:
    snapshot = await build_reflection_input_snapshot(
        session,
        as_of=as_of,
        lookback_days=lookback_days,
    )
    result = await completer(
        module="learning_reflection",
        options=LLMCompletionOptions(
            messages=[
                LLMMessage(role="system", content=REFLECTION_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=json.dumps(snapshot.to_payload(), ensure_ascii=False),
                ),
            ],
            temperature=0.1,
            max_tokens=1200,
            json_mode=True,
            json_schema=REFLECTION_JSON_SCHEMA,
        ),
        session=session,
    )
    candidates = parse_reflection_candidates(result.content)
    return await persist_learning_hypotheses(
        session,
        candidates,
        source_payload={
            "model": result.model,
            "period_start": snapshot.period_start.isoformat(),
            "period_end": snapshot.period_end.isoformat(),
            "input_counts": {
                "signals": len(snapshot.signals),
                "recommendations": len(snapshot.recommendations),
                "feedback": len(snapshot.feedback),
                "drift": len(snapshot.drift),
            },
        },
    )


async def build_reflection_input_snapshot(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    max_rows: int = 200,
) -> ReflectionInputSnapshot:
    period_end = as_of or datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=lookback_days)
    signal_rows = (
        await session.scalars(
            select(SignalTrack)
            .where(SignalTrack.created_at >= period_start, SignalTrack.created_at <= period_end)
            .order_by(SignalTrack.created_at.desc())
            .limit(max_rows)
        )
    ).all()
    recommendation_rows = (
        await session.scalars(
            select(Recommendation)
            .where(
                Recommendation.created_at >= period_start,
                Recommendation.created_at <= period_end,
            )
            .order_by(Recommendation.created_at.desc())
            .limit(max_rows)
        )
    ).all()
    feedback_rows = (
        await session.scalars(
            select(UserFeedback)
            .where(
                UserFeedback.recorded_at >= period_start,
                UserFeedback.recorded_at <= period_end,
            )
            .order_by(UserFeedback.recorded_at.desc())
            .limit(max_rows)
        )
    ).all()
    drift_rows = (
        await session.scalars(
            select(DriftMetric)
            .where(DriftMetric.computed_at >= period_start, DriftMetric.computed_at <= period_end)
            .order_by(DriftMetric.computed_at.desc())
            .limit(max_rows)
        )
    ).all()
    return ReflectionInputSnapshot(
        period_start=period_start,
        period_end=period_end,
        signals=[_sanitize_signal(row) for row in signal_rows],
        recommendations=[_sanitize_recommendation(row) for row in recommendation_rows],
        feedback=[_sanitize_feedback(row) for row in feedback_rows],
        drift=[_sanitize_drift(row) for row in drift_rows],
    )


def parse_reflection_candidates(content: str) -> list[LearningHypothesisCandidate]:
    data = json.loads(content)
    raw_items = data.get("hypotheses", data) if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        raise ValueError("Reflection response must contain a hypotheses list")
    candidates: list[LearningHypothesisCandidate] = []
    for item in raw_items:
        try:
            candidates.append(LearningHypothesisCandidate.model_validate(item))
        except ValidationError:
            continue
    return candidates


async def persist_learning_hypotheses(
    session: AsyncSession,
    candidates: list[LearningHypothesisCandidate],
    *,
    source_payload: dict[str, Any] | None = None,
) -> ReflectionAgentResult:
    proposed = 0
    rejected = 0
    weak_evidence = 0
    review_queued = 0
    hypothesis_ids: list[str] = []
    for candidate in candidates:
        status, evidence_strength, rejection_reason = classify_candidate(candidate)
        row = LearningHypothesis(
            id=uuid4(),
            hypothesis=candidate.hypothesis,
            supporting_evidence=list(candidate.supporting_evidence),
            proposed_change=candidate.proposed_change,
            confidence=candidate.confidence,
            sample_size=candidate.sample_size,
            counterevidence=list(candidate.counterevidence_considered),
            status=status,
            evidence_strength=evidence_strength,
            rejection_reason=rejection_reason,
            source_payload=source_payload or {},
        )
        session.add(row)
        await session.flush()
        await record_hypothesis_vector_chunk(session, row)
        hypothesis_ids.append(str(row.id))
        if evidence_strength == "weak_evidence":
            weak_evidence += 1
        if status == "rejected":
            rejected += 1
            continue

        await enqueue_review(
            session,
            source="llm_agent",
            target_table="learning_hypotheses",
            target_key=str(row.id),
            proposed_change={
                "hypothesis_id": str(row.id),
                "hypothesis": row.hypothesis,
                "proposed_change": row.proposed_change,
                "confidence": row.confidence,
                "sample_size": row.sample_size,
                "evidence_strength": row.evidence_strength,
            },
            reason="LLM reflection output requires human review before shadow testing.",
        )
        proposed += 1
        review_queued += 1

    return ReflectionAgentResult(
        generated=len(candidates),
        proposed=proposed,
        rejected=rejected,
        weak_evidence=weak_evidence,
        review_queued=review_queued,
        hypothesis_ids=hypothesis_ids,
    )


async def record_hypothesis_vector_chunk(
    session: AsyncSession,
    row: LearningHypothesis,
) -> VectorChunk:
    chunk = VectorChunk(
        chunk_type="learning_hypothesis",
        source_id=row.id,
        content_text="\n".join(
            item
            for item in (
                row.hypothesis,
                row.proposed_change or "",
                "Counterevidence: " + "; ".join(row.counterevidence),
            )
            if item
        ),
        embedding=None,
        embedding_model=None,
        metadata_json={
            "source": "llm_reflection",
            "status": row.status,
            "evidence_strength": row.evidence_strength,
        },
        quality_status="unverified",
    )
    session.add(chunk)
    await session.flush()
    return chunk


def classify_candidate(candidate: LearningHypothesisCandidate) -> tuple[str, str, str | None]:
    evidence_strength = (
        "weak_evidence"
        if candidate.sample_size < WEAK_EVIDENCE_MIN_SAMPLES
        else "sufficient_evidence"
    )
    text = " ".join(
        item
        for item in (
            candidate.hypothesis,
            candidate.proposed_change or "",
            *candidate.supporting_evidence,
        )
    ).lower()
    for term in BANNED_AUTOMATION_TERMS:
        if term.lower() in text:
            return "rejected", evidence_strength, "unsafe_auto_apply_language"
    if len(candidate.counterevidence_considered) < 2:
        return "rejected", evidence_strength, "missing_counterevidence"
    return "proposed", evidence_strength, None


def _sanitize_signal(row: SignalTrack) -> dict[str, Any]:
    return {
        "signal_type": row.signal_type,
        "category": row.category,
        "confidence": round(float(row.confidence), 4),
        "outcome": row.outcome,
        "regime": row.regime_at_emission or row.regime,
        "forward_return_1d": row.forward_return_1d,
        "forward_return_5d": row.forward_return_5d,
        "forward_return_20d": row.forward_return_20d,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _sanitize_recommendation(row: Recommendation) -> dict[str, Any]:
    return {
        "status": row.status,
        "recommended_action": row.recommended_action,
        "priority_score": row.priority_score,
        "portfolio_fit_score": row.portfolio_fit_score,
        "margin_efficiency_score": row.margin_efficiency_score,
        "relative_return": _relative_return(row),
        "mae": row.mae,
        "mfe": row.mfe,
        "holding_period_days": row.holding_period_days,
        "actual_exit_reason": row.actual_exit_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _sanitize_feedback(row: UserFeedback) -> dict[str, Any]:
    return {
        "signal_type": row.signal_type,
        "category": row.category,
        "agree": row.agree,
        "will_trade": row.will_trade,
        "disagreement_reason": row.disagreement_reason,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
    }


def _sanitize_drift(row: DriftMetric) -> dict[str, Any]:
    return {
        "metric_type": row.metric_type,
        "category": row.category,
        "feature_name": row.feature_name,
        "psi": row.psi,
        "drift_severity": row.drift_severity,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def _relative_return(row: Recommendation) -> float | None:
    if row.actual_entry is None or row.actual_exit is None or row.actual_entry == 0:
        return None
    direction = _recommendation_direction(row)
    raw_return = (row.actual_exit - row.actual_entry) / abs(row.actual_entry)
    return round(raw_return * direction, 6)


def _recommendation_direction(row: Recommendation) -> int:
    for leg in row.legs or []:
        direction = str(leg.get("direction") or "").lower()
        if direction == "short":
            return -1
        if direction == "long":
            return 1
    return 1


REFLECTION_SYSTEM_PROMPT = """
You are Zeus's monthly reflection agent. Generate falsifiable research hypotheses only.
Do not recommend immediate or automatic parameter changes. Every hypothesis must include at
least two counterevidence items or alternative explanations. Use only relative outcomes from
the sanitized payload; never infer account size or trade amount.
Return strict JSON with a top-level "hypotheses" array.
"""

REFLECTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis": {"type": "string"},
                    "supporting_evidence": {"type": "array", "items": {"type": "string"}},
                    "proposed_change": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                    "counterevidence_considered": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "sample_size": {"type": "integer"},
                },
                "required": [
                    "hypothesis",
                    "supporting_evidence",
                    "confidence",
                    "counterevidence_considered",
                    "sample_size",
                ],
            },
        }
    },
    "required": ["hypotheses"],
}
