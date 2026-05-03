import asyncio
import inspect
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.redis import get_redis
from app.models.event_log import EventLog

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Awaitable[None] | None]


@dataclass(frozen=True)
class ZeusEvent:
    channel: str
    payload: dict[str, Any]
    source: str = "zeus"
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            object.__setattr__(self, "correlation_id", str(self.id))
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeusEvent":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(timezone.utc)

        event_id = data.get("id")
        return cls(
            id=UUID(str(event_id)) if event_id else uuid4(),
            channel=str(data["channel"]),
            timestamp=timestamp,
            source=str(data.get("source") or "zeus"),
            payload=dict(data.get("payload") or {}),
            correlation_id=str(data.get("correlation_id") or event_id or uuid4()),
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "ZeusEvent":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.from_dict(json.loads(raw))


async def record_event(
    session: AsyncSession,
    event: ZeusEvent,
    *,
    status: str,
    error: str | None = None,
) -> EventLog:
    row = EventLog(
        event_id=event.id,
        channel=event.channel,
        source=event.source,
        correlation_id=event.correlation_id or str(event.id),
        payload=event.payload,
        status=status,
        error=error,
    )
    session.add(row)
    await session.flush()
    return row


async def publish(
    channel: str,
    payload: dict[str, Any],
    *,
    source: str = "zeus",
    correlation_id: str | None = None,
    session: AsyncSession | None = None,
    redis_client: Redis | None = None,
) -> ZeusEvent:
    event = ZeusEvent(
        channel=channel,
        payload=payload,
        source=source,
        correlation_id=correlation_id,
    )
    client = redis_client or get_redis()

    try:
        await client.publish(channel, event.to_json())
    except Exception as exc:
        if session is not None:
            await record_event(session, event, status="dead_letter", error=str(exc))
        raise

    if session is not None:
        await record_event(session, event, status="published")
    return event


async def dispatch_event(
    event: ZeusEvent,
    handler: EventHandler,
    *,
    session: AsyncSession | None = None,
) -> None:
    try:
        result = _call_handler(handler, event, session)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        if session is not None:
            await record_event(session, event, status="dead_letter", error=str(exc))
        raise

    if session is not None:
        await record_event(session, event, status="handled")


def _call_handler(
    handler: EventHandler,
    event: ZeusEvent,
    session: AsyncSession | None,
) -> Awaitable[None] | None:
    if session is None:
        return handler(event)

    signature = inspect.signature(handler)
    parameters = signature.parameters
    if any(param.kind is inspect.Parameter.VAR_POSITIONAL for param in parameters.values()):
        return handler(event, session)
    if "session" in parameters:
        return handler(event, session=session)

    positional = [
        param
        for param in parameters.values()
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return handler(event, session)
    return handler(event)


async def subscribe(
    channel: str,
    handler: EventHandler,
    *,
    redis_client: Redis | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    client = redis_client or get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    logger.info("Subscribed to Redis channel %s", channel)

    try:
        while stop_event is None or not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            event = ZeusEvent.from_json(message["data"])
            if session_factory is None:
                try:
                    await dispatch_event(event, handler)
                except Exception:
                    logger.exception("Event handler failed for channel %s", channel)
                continue

            async with session_factory() as session:
                try:
                    await dispatch_event(event, handler, session=session)
                except Exception:
                    await session.commit()
                    logger.exception("Event handler failed for channel %s", channel)
                else:
                    await session.commit()
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


async def iter_events(
    channel: str,
    *,
    redis_client: Redis | None = None,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[ZeusEvent]:
    client = redis_client or get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)

    try:
        while stop_event is None or not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None:
                yield ZeusEvent.from_json(message["data"])
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
