from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.feedback import require_feedback_targets
from app.models.alert import Alert
from app.models.recommendation import Recommendation
from app.models.user_feedback import UserFeedback
from app.schemas.common import UserFeedbackCreate
from app.services.learning.user_feedback import record_user_feedback


class FakeSession:
    def __init__(self, alert: Alert | None = None, recommendation: Recommendation | None = None) -> None:
        self.alert = alert
        self.recommendation = recommendation
        self.rows: list[object] = []
        self.flush_count = 0

    async def get(self, model, _):
        if model is Alert:
            return self.alert
        if model is Recommendation:
            return self.recommendation
        return None

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


async def test_record_user_feedback_copies_alert_signal_metadata() -> None:
    alert = Alert(
        id=uuid4(),
        title="SC supply news",
        summary="Supply signal.",
        severity="high",
        category="energy",
        type="news_event",
        status="active",
        triggered_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        confidence=0.82,
        related_assets=["SC"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    session = FakeSession(alert)

    row = await record_user_feedback(
        session,  # type: ignore[arg-type]
        alert_id=alert.id,
        agree="agree",
        will_trade="will_trade",
    )

    assert isinstance(row, UserFeedback)
    assert row.signal_type == "news_event"
    assert row.category == "energy"
    assert session.flush_count == 1


def _feedback_payload(**overrides) -> UserFeedbackCreate:
    values = {
        "agree": "agree",
        "will_trade": "will_trade",
    }
    values.update(overrides)
    return UserFeedbackCreate(**values)


async def test_feedback_requires_alert_or_recommendation_target() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_feedback_targets(
            FakeSession(),  # type: ignore[arg-type]
            _feedback_payload(),
        )

    assert exc_info.value.status_code == 400


async def test_feedback_rejects_missing_alert_target() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_feedback_targets(
            FakeSession(),  # type: ignore[arg-type]
            _feedback_payload(alert_id=uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Alert not found"


async def test_feedback_accepts_existing_recommendation_target() -> None:
    recommendation = Recommendation(
        id=uuid4(),
        status="pending",
        recommended_action="open_spread",
        legs=[{"asset": "RB", "direction": "long"}],
        priority_score=80,
        portfolio_fit_score=70,
        margin_efficiency_score=75,
        margin_required=10_000,
        reasoning="feedback target",
        risk_items=[],
        expires_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
    )

    await require_feedback_targets(
        FakeSession(recommendation=recommendation),  # type: ignore[arg-type]
        _feedback_payload(recommendation_id=recommendation.id),
    )
