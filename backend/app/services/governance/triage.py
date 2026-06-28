from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FORCE_PENDING_SOURCES = {
    "backtest_live_divergence",
    "calibration",
    "forecast_promotion",
    "llm_agent",
    "signal_calibration",
    "threshold_calibration",
    "trade_plan_review",
}

HUMAN_PENDING_ATTENTION_THRESHOLD = 70.0
SHADOW_REVIEW_ATTENTION_THRESHOLD = 45.0


@dataclass(frozen=True)
class ReviewTriageResult:
    attention_score: float
    tier: str
    queue_status: str | None
    reasons: list[str]

    @property
    def requires_human_attention(self) -> bool:
        return self.queue_status == "pending"

    def to_payload(self) -> dict[str, Any]:
        return {
            "attention_score": self.attention_score,
            "tier": self.tier,
            "queue_status": self.queue_status,
            "requires_human_attention": self.requires_human_attention,
            "reasons": list(self.reasons),
        }


def triage_change_review(
    *,
    source: str,
    proposed_change: dict[str, Any],
    default_status: str = "pending",
) -> ReviewTriageResult:
    if source in FORCE_PENDING_SOURCES:
        return ReviewTriageResult(
            attention_score=100.0,
            tier="must_review",
            queue_status="pending",
            reasons=["production_or_model_change"],
        )

    review_triage = proposed_change.get("review_triage")
    if isinstance(review_triage, dict):
        score = _bounded_score(review_triage.get("attention_score"))
        requested_status = review_triage.get("queue_status")
        if requested_status in {"pending", "shadow_review"}:
            queue_status = str(requested_status)
        elif requested_status in {"evidence_only", None}:
            queue_status = None if requested_status == "evidence_only" else default_status
        else:
            queue_status = default_status
        return ReviewTriageResult(
            attention_score=score,
            tier=str(review_triage.get("tier") or _tier_for_score(score, queue_status)),
            queue_status=queue_status,
            reasons=[str(reason) for reason in review_triage.get("reasons", []) if reason],
        )

    return ReviewTriageResult(
        attention_score=100.0 if default_status == "pending" else 50.0,
        tier="must_review" if default_status == "pending" else "shadow_review",
        queue_status=default_status,
        reasons=["legacy_review_request"],
    )


def triage_event_intelligence(
    *,
    source_type: str | None = None,
    impact_score: float,
    confidence: float,
    source_reliability: float,
    freshness_score: float,
    review_reasons: list[str],
    link_count: int,
    max_link_impact: float = 0.0,
    manual_operator_action: bool = False,
) -> ReviewTriageResult:
    if manual_operator_action:
        return ReviewTriageResult(
            attention_score=100.0,
            tier="must_review",
            queue_status="pending",
            reasons=["manual_operator_action", *review_reasons],
        )
    normalized_source_type = str(source_type or "").strip().lower()
    auto_evidence_source = normalized_source_type in {"industry_data", "market", "weather"}
    if (
        not auto_evidence_source
        and
        "high_impact_uncertain_event" in review_reasons
        and impact_score >= 90
        and confidence >= 0.75
        and source_reliability >= 0.6
    ):
        return ReviewTriageResult(
            attention_score=100.0,
            tier="must_review",
            queue_status="pending",
            reasons=["high_trust_extreme_event", *list(dict.fromkeys(review_reasons))],
        )

    score = 0.0
    score += _bounded_score(impact_score) * 0.36
    score += _bounded_score(confidence * 100) * 0.18
    score += _bounded_score(source_reliability * 100) * 0.14
    score += _bounded_score(freshness_score * 100) * 0.10
    score += _bounded_score(max_link_impact) * 0.10
    score += min(12.0, max(0, link_count - 1) * 2.0)

    if "high_impact_uncertain_event" in review_reasons:
        score += 18.0
    if "impact_link_requires_review" in review_reasons:
        score += 6.0
    if "single_source" in review_reasons:
        score -= 8.0
    if "low_confidence" in review_reasons:
        score -= 8.0
    if "low_source_reliability" in review_reasons:
        score -= 6.0

    score = _bounded_score(score)
    if auto_evidence_source:
        score = min(score, SHADOW_REVIEW_ATTENTION_THRESHOLD + 10.0)
    if score >= HUMAN_PENDING_ATTENTION_THRESHOLD:
        queue_status: str | None = "pending"
        tier = "must_review"
    elif score >= SHADOW_REVIEW_ATTENTION_THRESHOLD:
        queue_status = "shadow_review"
        tier = "shadow_review"
    else:
        queue_status = None
        tier = "evidence_only"

    return ReviewTriageResult(
        attention_score=round(score, 2),
        tier=tier,
        queue_status=queue_status,
        reasons=list(dict.fromkeys(review_reasons)),
    )


def _tier_for_score(score: float, queue_status: str | None) -> str:
    if queue_status == "pending":
        return "must_review"
    if queue_status == "shadow_review":
        return "shadow_review"
    if score >= HUMAN_PENDING_ATTENTION_THRESHOLD:
        return "must_review"
    if score >= SHADOW_REVIEW_ATTENTION_THRESHOLD:
        return "shadow_review"
    return "evidence_only"


def _bounded_score(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(100.0, max(0.0, parsed))
