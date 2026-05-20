from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.recommendations import apply_recommendation_review, require_adoptable_recommendation
from app.models.alert import Alert
from app.models.alert_agent import HumanDecision
from app.models.recommendation import Recommendation
from app.schemas.common import RecommendationRead, RecommendationReviewRequest


class FakeSession:
    def __init__(self, row: Recommendation | None, alert: Alert | None = None) -> None:
        self.row = row
        self.alert = alert
        self.added: list[object] = []
        self.flush_count = 0

    async def get(self, model, _):
        if model is Alert:
            return self.alert
        return self.row

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


def _recommendation(
    *,
    status: str = "pending",
    expires_at: datetime | None = None,
    alert_id=None,
) -> Recommendation:
    return Recommendation(
        id=uuid4(),
        alert_id=alert_id,
        status=status,
        recommended_action="open_spread",
        legs=[{"asset": "RB", "direction": "long"}],
        priority_score=80,
        portfolio_fit_score=70,
        margin_efficiency_score=75,
        margin_required=10_000,
        reasoning="adoptable recommendation",
        risk_items=[],
        expires_at=expires_at or datetime(2026, 5, 5, tzinfo=timezone.utc),
        entry_price=3200,
    )


def _alert(alert_id) -> Alert:
    return Alert(
        id=alert_id,
        title="RB review signal",
        summary="Needs review.",
        severity="high",
        category="ferrous",
        type="spread_anomaly",
        status="pending",
        triggered_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        confidence=0.72,
        adversarial_passed=True,
        llm_involved=True,
        confidence_tier="auto",
        human_action_required=True,
        dedup_suppressed=False,
        related_assets=["RB", "HC"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )


async def test_pending_recommendation_can_be_adopted_before_expiry() -> None:
    row = _recommendation()

    result = await require_adoptable_recommendation(
        FakeSession(row),  # type: ignore[arg-type]
        row.id,
        as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )

    assert result is row


async def test_non_pending_recommendation_cannot_be_adopted_again() -> None:
    row = _recommendation(status="accepted")

    with pytest.raises(HTTPException) as exc_info:
        await require_adoptable_recommendation(
            FakeSession(row),  # type: ignore[arg-type]
            row.id,
            as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Recommendation is not pending"


async def test_expired_recommendation_cannot_be_adopted() -> None:
    row = _recommendation(expires_at=datetime(2026, 5, 3, tzinfo=timezone.utc))

    with pytest.raises(HTTPException) as exc_info:
        await require_adoptable_recommendation(
            FakeSession(row),  # type: ignore[arg-type]
            row.id,
            as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Recommendation has expired"


async def test_pending_review_recommendation_can_be_approved_for_adoption() -> None:
    alert_id = uuid4()
    row = _recommendation(
        status="pending_review",
        alert_id=alert_id,
        expires_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
    )
    row.backtest_summary = {"review_required": True, "review_reasons": ["manual"]}
    alert = _alert(alert_id)
    session = FakeSession(row, alert)

    result = await apply_recommendation_review(
        session,  # type: ignore[arg-type]
        row.id,
        RecommendationReviewRequest(
            decision="approve",
            reviewed_by="tester",
            reason="looks actionable",
            confidence_override=0.86,
        ),
        as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )

    assert result.status == "pending"
    assert result.backtest_summary["review_required"] is False
    assert result.backtest_summary["review_reasons"] == []
    assert result.backtest_summary["review_decision"]["decision"] == "approve"
    assert alert.status == "active"
    assert alert.human_action_required is False
    assert alert.confidence == 0.86
    assert any(isinstance(item, HumanDecision) and item.decision == "approve" for item in session.added)


async def test_pending_review_recommendation_can_be_rejected() -> None:
    alert_id = uuid4()
    row = _recommendation(status="pending_review", alert_id=alert_id)
    alert = _alert(alert_id)
    session = FakeSession(row, alert)

    result = await apply_recommendation_review(
        session,  # type: ignore[arg-type]
        row.id,
        RecommendationReviewRequest(
            decision="reject",
            reviewed_by="tester",
            reason="event is stale",
        ),
        as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )

    assert result.status == "ignored"
    assert result.ignored_reason == "event is stale"
    assert result.backtest_summary["review_required"] is True
    assert result.backtest_summary["review_reasons"] == ["人工驳回：event is stale"]
    assert alert.status == "dismissed"
    assert any(isinstance(item, HumanDecision) and item.decision == "reject" for item in session.added)


async def test_only_pending_review_recommendations_can_be_reviewed() -> None:
    row = _recommendation(status="pending")

    with pytest.raises(HTTPException) as exc_info:
        await apply_recommendation_review(
            FakeSession(row),  # type: ignore[arg-type]
            row.id,
            RecommendationReviewRequest(decision="approve"),
            as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Recommendation is not pending review"


def test_recommendation_read_truncates_legacy_oversized_risk_items() -> None:
    row = _recommendation()
    row.risk_items = [f"risk-{index}" for index in range(25)]
    row.created_at = datetime(2026, 5, 4, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 5, 4, tzinfo=timezone.utc)

    payload = RecommendationRead.model_validate(row)

    assert len(payload.risk_items) == 20
    assert payload.risk_items[-1] == "risk-19"
