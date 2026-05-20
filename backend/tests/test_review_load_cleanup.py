from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.alert import Alert
from app.models.recommendation import Recommendation
from app.services.governance.cleanup import (
    expire_alert_review_load,
    expire_recommendation_review_load,
)


def _alert(*, expires_at: datetime, status: str = "pending") -> Alert:
    return Alert(
        id=uuid4(),
        title="review alert",
        summary="needs review",
        severity="medium",
        category="rubber",
        type="inventory_shock",
        status=status,
        triggered_at=expires_at - timedelta(hours=2),
        expires_at=expires_at,
        confidence=0.5,
        human_action_required=True,
        human_action_deadline=expires_at - timedelta(hours=1),
        related_assets=["RU"],
    )


def test_expire_alert_review_load_releases_stale_pending_alert() -> None:
    as_of = datetime(2026, 5, 18, tzinfo=UTC)
    alert = _alert(expires_at=as_of - timedelta(minutes=1))

    changed = expire_alert_review_load(alert, as_of=as_of)

    assert changed is True
    assert alert.human_action_required is False
    assert alert.human_action_deadline is None
    assert alert.status == "expired"
    assert alert.invalidation_reason == "Expired before human review; removed from attention queue."


def test_expire_alert_review_load_expires_stale_active_alert() -> None:
    as_of = datetime(2026, 5, 18, tzinfo=UTC)
    alert = _alert(expires_at=as_of - timedelta(minutes=1), status="active")
    alert.human_action_required = False
    alert.human_action_deadline = None

    changed = expire_alert_review_load(alert, as_of=as_of)

    assert changed is True
    assert alert.status == "expired"
    assert alert.human_action_required is False
    assert alert.invalidation_reason == "Expired before execution; removed from active signal set."


def test_expire_alert_review_load_keeps_future_alert_in_queue() -> None:
    as_of = datetime(2026, 5, 18, tzinfo=UTC)
    alert = _alert(expires_at=as_of + timedelta(minutes=1))

    changed = expire_alert_review_load(alert, as_of=as_of)

    assert changed is False
    assert alert.human_action_required is True
    assert alert.status == "pending"


def test_expire_recommendation_review_load_expires_stale_pending_plan() -> None:
    as_of = datetime(2026, 5, 18, tzinfo=UTC)
    recommendation = Recommendation(
        id=uuid4(),
        status="pending",
        recommended_action="open_directional",
        legs=[{"asset": "RU", "direction": "long"}],
        priority_score=82,
        portfolio_fit_score=70,
        margin_efficiency_score=75,
        margin_required=100000,
        reasoning="actionable signal",
        risk_items=[],
        expires_at=as_of - timedelta(minutes=1),
        backtest_summary={"review_required": False},
    )

    changed = expire_recommendation_review_load(recommendation, as_of=as_of)

    assert changed is True
    assert recommendation.status == "expired"
    assert recommendation.ignored_reason == "Recommendation expired before adoption or review."
    assert recommendation.backtest_summary["previous_status"] == "pending"
    assert recommendation.backtest_summary["review_required"] is False


def test_expire_recommendation_review_load_keeps_completed_plan() -> None:
    as_of = datetime(2026, 5, 18, tzinfo=UTC)
    recommendation = Recommendation(
        id=uuid4(),
        status="completed",
        recommended_action="open_spread",
        legs=[{"asset": "RB", "direction": "long"}],
        priority_score=82,
        portfolio_fit_score=70,
        margin_efficiency_score=75,
        margin_required=100000,
        reasoning="closed plan",
        risk_items=[],
        expires_at=as_of - timedelta(minutes=1),
    )

    changed = expire_recommendation_review_load(recommendation, as_of=as_of)

    assert changed is False
    assert recommendation.status == "completed"
