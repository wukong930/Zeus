from uuid import UUID

import pytest

from app.core.events import ZeusEvent, dispatch_event, publish


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

    async def flush(self) -> None:
        self.flush_count += 1


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


async def test_publish_sends_to_redis_and_records_audit() -> None:
    redis = FakeRedis()
    session = FakeSession()

    event = await publish(
        "market.update",
        {"job_id": "ingest"},
        source="scheduler",
        session=session,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
    )

    assert redis.messages[0][0] == "market.update"
    assert ZeusEvent.from_json(redis.messages[0][1]).id == event.id
    assert session.rows[0].status == "published"
    assert session.rows[0].event_id == event.id
    assert session.flush_count == 1


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
