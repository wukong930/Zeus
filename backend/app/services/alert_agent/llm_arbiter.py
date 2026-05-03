import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.alert_agent.classifier import classify_alert
from app.services.alert_agent.narrative import generate_narrative
from app.services.llm.registry import complete_with_llm_controls
from app.services.llm.types import LLMCompletionOptions, LLMMessage
from app.services.vector_search.embedder import DeterministicHashEmbedder
from app.services.vector_search.hybrid_search import hybrid_search


class AlertArbitrationResult(BaseModel):
    classification: str = Field(pattern="^L[0-3]$")
    narrative: str
    risk_items: list[str] = Field(default_factory=list)
    manual_check_items: list[str] = Field(default_factory=list)
    confidence_adjustment: float = Field(default=1.0, ge=0.0, le=1.2)
    fallback_used: bool = False


async def arbitrate_signal(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    score: dict[str, Any] | Any | None = None,
) -> AlertArbitrationResult:
    historical_analogues = await historical_analogues_for_signal(session, signal)
    system = (
        "You are Zeus Alert Agent. Return strict JSON with classification, narrative, "
        "risk_items, manual_check_items, and confidence_adjustment."
    )
    user = json.dumps(
        {
            "signal": signal,
            "context": context,
            "score": score if isinstance(score, dict) else getattr(score, "__dict__", score),
            "historical_analogues": historical_analogues,
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        result = await complete_with_llm_controls(
            module="alert_agent",
            session=session,
            options=LLMCompletionOptions(
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
                temperature=0,
                max_tokens=800,
                json_mode=True,
                json_schema=AlertArbitrationResult.model_json_schema(),
            ),
        )
        return AlertArbitrationResult.model_validate_json(result.content)
    except (Exception, ValidationError):
        return deterministic_arbitration(signal, score)


async def historical_analogues_for_signal(
    session: AsyncSession | None,
    signal: dict[str, Any],
) -> list[dict[str, Any]]:
    if session is None:
        return []
    query_text = " ".join(
        str(item)
        for item in (
            signal.get("title", ""),
            signal.get("summary", ""),
            signal.get("signal_type", ""),
            " ".join(str(asset) for asset in signal.get("related_assets", [])),
        )
        if item
    ).strip()
    if not query_text:
        return []
    try:
        embedding = await DeterministicHashEmbedder().embed_text(query_text)
        rows = await hybrid_search(
            session,
            query_text=query_text,
            query_embedding=embedding.embedding,
            chunk_type="news",
            limit=3,
        )
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        return []
    return [
        {
            "source_id": str(row.source_id) if row.source_id else None,
            "content": row.content_text[:500],
            "quality_status": row.quality_status,
            "final_score": round(row.final_score, 4),
            "cosine_score": round(row.cosine_score, 4),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def deterministic_arbitration(
    signal: dict[str, Any],
    score: dict[str, Any] | Any | None = None,
) -> AlertArbitrationResult:
    classification = classify_alert(signal, score)
    return AlertArbitrationResult(
        classification=classification,
        narrative=generate_narrative(signal, classification),
        risk_items=[str(item) for item in signal.get("risk_items", [])],
        manual_check_items=[str(item) for item in signal.get("manual_check_items", [])],
        confidence_adjustment=1.0,
        fallback_used=True,
    )
