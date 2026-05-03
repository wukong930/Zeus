from datetime import datetime, timezone

from app.core.events import ZeusEvent
from app.models.alert import Alert
from app.services.pipeline.handlers import (
    handle_market_update,
    handle_news_event,
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

    async def scalars(self, _):
        return FakeScalars()

    async def flush(self) -> None:
        self.flush_count += 1


class FakeScalars:
    def first(self):
        return None


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


async def test_news_event_handler_publishes_news_signal() -> None:
    event = ZeusEvent(
        channel="news.event",
        payload={
            "news_event": {
                "id": "evt-1",
                "source": "cailianshe",
                "title": "OPEC+ extends production cuts",
                "summary": "OPEC+ extends production cuts, bullish for crude oil.",
                "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                "event_type": "supply",
                "affected_symbols": ["SC"],
                "direction": "bullish",
                "severity": 5,
                "time_horizon": "medium",
                "llm_confidence": 0.82,
                "source_count": 2,
                "verification_status": "cross_verified",
                "requires_manual_confirmation": False,
            },
            "contexts": [
                {
                    "symbol1": "SC",
                    "category": "energy",
                    "regime": "news",
                    "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                    "news_events": [
                        {
                            "id": "evt-1",
                            "source": "cailianshe",
                            "title": "OPEC+ extends production cuts",
                            "summary": "OPEC+ extends production cuts, bullish for crude oil.",
                            "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                            "event_type": "supply",
                            "affected_symbols": ["SC"],
                            "direction": "bullish",
                            "severity": 5,
                            "time_horizon": "medium",
                            "llm_confidence": 0.82,
                            "source_count": 2,
                            "verification_status": "cross_verified",
                            "requires_manual_confirmation": False,
                        }
                    ],
                }
            ],
        },
        source="test",
    )
    publisher = CapturingPublisher()

    published = await handle_news_event(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected"]
    assert publisher.calls[0]["event"].payload["signal"]["signal_type"] == "news_event"
    assert publisher.calls[0]["event"].payload["context"]["news_events"][0]["id"] == "evt-1"


async def test_news_event_handler_publishes_rubber_supply_signal() -> None:
    event_payload = {
        "id": "rubber-evt-1",
        "source": "rubber_supply_gdelt",
        "title": "Thailand floods disrupt natural rubber tapping",
        "summary": "Heavy rainfall in southern Thailand disrupts rubber tapping and exports.",
        "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
        "event_type": "weather",
        "affected_symbols": ["NR", "RU"],
        "direction": "bullish",
        "severity": 4,
        "time_horizon": "short",
        "llm_confidence": 0.78,
        "source_count": 2,
        "verification_status": "cross_verified",
        "requires_manual_confirmation": False,
    }
    event = ZeusEvent(
        channel="news.event",
        payload={
            "news_event": event_payload,
            "contexts": [
                {
                    "symbol1": "RU",
                    "category": "rubber",
                    "regime": "news",
                    "timestamp": event_payload["published_at"],
                    "news_events": [event_payload],
                }
            ],
        },
        source="test",
    )
    publisher = CapturingPublisher()

    published = await handle_news_event(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected", "signal.detected"]
    assert [call["event"].payload["signal"]["signal_type"] for call in publisher.calls] == [
        "news_event",
        "rubber_supply_shock",
    ]


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
    assert scored.payload["adversarial_result"]["passed"] is True
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
    assert session.rows[0].adversarial_passed is True
    assert created.payload["adversarial_passed"] is True
    assert created.payload["alert_id"] == str(session.rows[0].id)


async def test_signal_scored_handler_requests_scenario_for_arbitration_route() -> None:
    event = ZeusEvent(
        channel="signal.scored",
        payload={
            "signal": {
                "signal_type": "momentum",
                "severity": "high",
                "confidence": 0.72,
                "title": "RB bullish signal with bearish inventory conflict",
                "summary": "Momentum is bullish while inventory pressure is bearish.",
                "related_assets": ["RB"],
                "risk_items": [],
                "manual_check_items": [],
            },
            "context": {
                "category": "ferrous",
                "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                "market_data": [{"close": 3250}],
            },
            "score": {"priority": 75, "combined": 75},
        },
        source="test",
    )
    session = FakeSession()
    publisher = CapturingPublisher()

    created = await handle_signal_scored(
        event,
        session=session,  # type: ignore[arg-type]
        publisher=publisher,
    )

    assert created is not None
    assert created.channel == "alert.created"
    requested = next(call["event"] for call in publisher.calls if call["event"].channel == "scenario.requested")
    assert requested.payload["request"]["target_symbol"] == "RB"
    assert requested.payload["request"]["shocks"] == {"RB": 0.08}
    assert requested.payload["request"]["base_price"] == 3250
    assert requested.payload["trigger"]["route"] == "arbitrate"
