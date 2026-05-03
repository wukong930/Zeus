from datetime import datetime, timezone

from app.core.events import ZeusEvent
from app.models.alert import Alert
from app.services.pipeline.handlers import (
    handle_market_update,
    handle_signal_detected,
    handle_signal_scored,
)


class CapturingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, channel: str, payload: dict, **kwargs) -> ZeusEvent:
        event = ZeusEvent(
            channel=channel,
            payload=payload,
            source=kwargs.get("source", "test"),
            correlation_id=kwargs.get("correlation_id"),
        )
        self.calls.append({"event": event, "kwargs": kwargs})
        return event


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


def _market_update_event() -> ZeusEvent:
    return ZeusEvent(
        channel="market.update",
        payload={
            "contexts": [
                {
                    "symbol1": "RB",
                    "symbol2": "HC",
                    "category": "ferrous",
                    "regime": "range_low_vol",
                    "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                    "spread_stats": {
                        "adf_p_value": 0.03,
                        "half_life": 12,
                        "spread_mean": 10,
                        "spread_std_dev": 2,
                        "current_z_score": 2.8,
                    },
                }
            ]
        },
        source="test",
    )


async def test_market_update_handler_publishes_detected_signals() -> None:
    publisher = CapturingPublisher()

    published = await handle_market_update(_market_update_event(), publisher=publisher)

    assert [event.channel for event in published] == ["signal.detected", "signal.detected"]
    assert publisher.calls[0]["event"].payload["signal"]["signal_type"] == "spread_anomaly"
    assert publisher.calls[0]["event"].payload["context"]["symbol1"] == "RB"
    assert publisher.calls[0]["event"].payload["context"]["regime"] == "range_low_vol"


async def test_signal_detected_handler_publishes_score() -> None:
    publisher = CapturingPublisher()
    detected = (await handle_market_update(_market_update_event(), publisher=publisher))[0]
    score_publisher = CapturingPublisher()

    scored = await handle_signal_detected(
        detected,
        publisher=score_publisher,
    )

    assert scored is not None
    assert scored.channel == "signal.scored"
    assert scored.payload["recommended_action"] == "open_spread"
    assert scored.payload["score"]["priority"] > 0
    assert scored.payload["legs"][0]["asset"] == "RB"


async def test_signal_scored_handler_creates_alert_and_publishes_event() -> None:
    signal_publisher = CapturingPublisher()
    detected = (await handle_market_update(_market_update_event(), publisher=signal_publisher))[0]
    score_publisher = CapturingPublisher()
    scored = await handle_signal_detected(detected, publisher=score_publisher)
    assert scored is not None

    session = FakeSession()
    alert_publisher = CapturingPublisher()
    created = await handle_signal_scored(
        scored,
        session=session,  # type: ignore[arg-type]
        publisher=alert_publisher,
    )

    assert created is not None
    assert created.channel == "alert.created"
    assert isinstance(session.rows[0], Alert)
    assert session.rows[0].type == "spread_anomaly"
    assert created.payload["alert_id"] == str(session.rows[0].id)
