from uuid import UUID

import pytest

from app.api.alerts import format_sse_event
from app.core.events import ZeusEvent, dispatch_event, publish, publish_pending_events


class FakeRedis:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.messages.append((channel, message))
        return 1


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def scalars(self, _):
        return FakeScalars([row for row in self.rows if getattr(row, "status", None) == "pending"])

    async def flush(self) -> None:
        self.flush_count += 1


class FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


def test_zeus_event_round_trips_json() -> None:
    event = ZeusEvent(
        channel="market.update",
        payload={"symbols": ["RB", "HC"]},
        source="scheduler",
    )

    restored = ZeusEvent.from_json(event.to_json())

    assert restored.id == event.id
    assert restored.channel == "market.update"
    assert restored.payload == {"symbols": ["RB", "HC"]}
    assert restored.correlation_id == str(event.id)


def test_format_sse_event_uses_alert_channel_and_json_payload() -> None:
    event = ZeusEvent(
        channel="alert.created",
        payload={"alert_id": "a1", "severity": "high"},
        source="alert-service",
    )

    payload = format_sse_event(event)

    assert payload.startswith(f"id: {event.id}\n")
    assert "event: alert.created\n" in payload
    assert '"severity": "high"' in payload
    assert payload.endswith("\n\n")


async def test_publish_with_session_records_pending_outbox_event() -> None:
    redis = FakeRedis()
    session = FakeSession()

    event = await publish(
        "market.update",
        {"job_id": "ingest"},
        source="scheduler",
        session=session,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
    )

    assert redis.messages == []
    assert session.rows[0].status == "pending"
    assert session.rows[0].event_id == event.id
    assert session.flush_count == 1


async def test_publish_pending_events_emits_and_marks_published() -> None:
    redis = FakeRedis()
    session = FakeSession()

    event = await publish(
        "market.update",
        {"job_id": "ingest"},
        source="scheduler",
        session=session,  # type: ignore[arg-type]
    )

    published = await publish_pending_events(
        session,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
    )

    assert published == 1
    assert redis.messages[0][0] == "market.update"
    assert ZeusEvent.from_json(redis.messages[0][1]).id == event.id
    assert session.rows[0].status == "published"


async def test_dispatch_event_records_handled_status() -> None:
    session = FakeSession()
    event = ZeusEvent(channel="signal.detected", payload={"signal_type": "momentum"})
    handled: list[UUID] = []

    async def handler(received: ZeusEvent) -> None:
        handled.append(received.id)

    await dispatch_event(event, handler, session=session)  # type: ignore[arg-type]

    assert handled == [event.id]
    assert session.rows[0].status == "handled"


async def test_dispatch_event_records_dead_letter_on_handler_error() -> None:
    session = FakeSession()
    event = ZeusEvent(channel="signal.detected", payload={"signal_type": "momentum"})

    async def handler(_: ZeusEvent) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await dispatch_event(event, handler, session=session)  # type: ignore[arg-type]

    assert session.rows[0].status == "dead_letter"
    assert session.rows[0].error == "boom"
