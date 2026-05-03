from datetime import datetime, timezone
from uuid import uuid4

from app.models.alert import Alert
from app.models.user_feedback import UserFeedback
from app.services.learning.user_feedback import record_user_feedback


class FakeSession:
    def __init__(self, alert: Alert) -> None:
        self.alert = alert
        self.rows: list[object] = []
        self.flush_count = 0

    async def get(self, _, __):
        return self.alert

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
