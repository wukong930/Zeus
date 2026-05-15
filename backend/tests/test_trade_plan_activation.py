from uuid import uuid4

from app.models.event_log import EventLog
from app.services.trade_plans.activation import TradePlanActivationResult, alert_id_from_event


def test_trade_plan_activation_result_payload_is_scheduler_friendly() -> None:
    result = TradePlanActivationResult(scanned=3, created=1, skipped_stale=2)

    assert result.to_dict() == {
        "status": "completed",
        "scanned": 3,
        "created": 1,
        "linked_existing": 0,
        "skipped_existing": 0,
        "skipped_missing_alert": 0,
        "skipped_ineligible": 0,
        "skipped_stale": 2,
    }


def test_alert_id_from_event_parses_valid_payload_and_ignores_bad_payload() -> None:
    alert_id = uuid4()

    assert (
        alert_id_from_event(
            EventLog(
                event_id=uuid4(),
                channel="alert.created",
                source="test",
                correlation_id="corr",
                payload={"alert_id": str(alert_id)},
                status="published",
            )
        )
        == alert_id
    )
    assert (
        alert_id_from_event(
            EventLog(
                event_id=uuid4(),
                channel="alert.created",
                source="test",
                correlation_id="corr",
                payload={"alert_id": "not-a-uuid"},
                status="published",
            )
        )
        is None
    )
