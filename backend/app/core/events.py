import asyncio
import inspect
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.exceptions import ResponseError
from redis.asyncio import Redis
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.core.redis import get_redis
from app.models.event_log import EventLog

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Awaitable[None] | None]
STREAM_MAXLEN = 10_000
STREAM_IDLE_MS = 60_000
PENDING_RELAY_INTERVAL_SECONDS = 0.5


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


def stream_key_for(channel: str) -> str:
    return f"zeus:events:{channel}"


def stream_group_for(channel: str) -> str:
    return f"zeus:{channel}"


async def emit_event(
    event: ZeusEvent,
    *,
    redis_client: Redis | None = None,
) -> None:
    client = redis_client or get_redis()
    payload = event.to_json()
    if hasattr(client, "xadd"):
        await client.xadd(
            stream_key_for(event.channel),
            {"event": payload},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
    await client.publish(event.channel, payload)


def event_from_log(row: EventLog) -> ZeusEvent:
    return ZeusEvent(
        id=row.event_id,
        channel=row.channel,
        timestamp=row.created_at or datetime.now(timezone.utc),
        source=row.source,
        payload=dict(row.payload or {}),
        correlation_id=row.correlation_id,
    )


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

    if session is not None:
        await record_event(session, event, status="pending")
        return event

    try:
        await emit_event(event, redis_client=redis_client)
    except Exception:
        raise
    return event


async def publish_pending_events(
    session: AsyncSession,
    *,
    redis_client: Redis | None = None,
    limit: int = 100,
) -> int:
    rows = (
        await session.scalars(
            select(EventLog)
            .where(EventLog.status == "pending")
            .order_by(EventLog.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    published = 0
    for row in rows:
        event = event_from_log(row)
        try:
            await emit_event(event, redis_client=redis_client)
        except Exception as exc:
            row.status = "dead_letter"
            row.error = str(exc)
            row.created_at = datetime.now(timezone.utc)
            continue
        row.status = "published"
        row.error = None
        row.created_at = datetime.now(timezone.utc)
        published += 1
    await session.flush()
    return published


async def replay_unhandled_events(
    session: AsyncSession,
    *,
    channels: tuple[str, ...],
    redis_client: Redis | None = None,
    limit: int = 100,
) -> int:
    if not channels:
        return 0
    published = aliased(EventLog)
    handled = aliased(EventLog)
    dead_letter = aliased(EventLog)
    rows = (
        await session.scalars(
            select(published)
            .where(
                published.status == "published",
                published.channel.in_(channels),
                ~exists(
                    select(handled.id).where(
                        handled.event_id == published.event_id,
                        handled.status == "handled",
                    )
                ),
                ~exists(
                    select(dead_letter.id).where(
                        dead_letter.event_id == published.event_id,
                        dead_letter.status == "dead_letter",
                    )
                ),
            )
            .order_by(published.created_at.asc())
            .limit(limit)
        )
    ).all()
    for row in rows:
        await emit_event(event_from_log(row), redis_client=redis_client)
    return len(rows)


async def relay_pending_events(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis | None = None,
    stop_event: asyncio.Event | None = None,
    poll_interval: float = PENDING_RELAY_INTERVAL_SECONDS,
) -> None:
    client = redis_client or get_redis()
    while stop_event is None or not stop_event.is_set():
        published = 0
        try:
            async with session_factory() as session:
                published = await publish_pending_events(session, redis_client=client)
                await session.commit()
        except Exception:
            logger.exception("Pending event relay failed")
        if published:
            continue
        if stop_event is None:
            await asyncio.sleep(poll_interval)
        else:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except TimeoutError:
                pass


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
            rollback = getattr(session, "rollback", None)
            if rollback is not None:
                await rollback()
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
    if not hasattr(client, "xreadgroup"):
        await _subscribe_pubsub(
            channel,
            handler,
            redis_client=client,
            session_factory=session_factory,
            stop_event=stop_event,
        )
        return

    key = stream_key_for(channel)
    group = stream_group_for(channel)
    consumer = f"consumer-{uuid4()}"
    await ensure_stream_group(client, key=key, group=group)

    logger.info("Subscribed to Redis stream %s group %s", key, group)
    while stop_event is None or not stop_event.is_set():
        claimed = await claim_idle_stream_messages(
            client,
            key=key,
            group=group,
            consumer=consumer,
        )
        if claimed:
            try:
                await handle_stream_messages(
                    claimed,
                    key=key,
                    group=group,
                    handler=handler,
                    session_factory=session_factory,
                    redis_client=client,
                )
            except Exception:
                logger.exception("Event stream claim handling failed for channel %s", channel)
            continue

        response = await client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={key: ">"},
            count=10,
            block=1000,
        )
        for _, messages in response or []:
            try:
                await handle_stream_messages(
                    messages,
                    key=key,
                    group=group,
                    handler=handler,
                    session_factory=session_factory,
                    redis_client=client,
                )
            except Exception:
                logger.exception("Event stream handling failed for channel %s", channel)


async def ensure_stream_group(client: Redis, *, key: str, group: str) -> None:
    try:
        await client.xgroup_create(key, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def claim_idle_stream_messages(
    client: Redis,
    *,
    key: str,
    group: str,
    consumer: str,
) -> list[tuple[str, dict[str, Any]]]:
    try:
        result = await client.xautoclaim(
            key,
            group,
            consumer,
            min_idle_time=STREAM_IDLE_MS,
            start_id="0-0",
            count=10,
        )
    except ResponseError as exc:
        if "NOGROUP" in str(exc):
            await ensure_stream_group(client, key=key, group=group)
            return []
        raise
    if len(result) >= 2:
        return list(result[1])
    return []


async def handle_stream_messages(
    messages: list[tuple[str, dict[str, Any]]],
    *,
    key: str,
    group: str,
    handler: EventHandler,
    session_factory: async_sessionmaker[AsyncSession] | None,
    redis_client: Redis,
) -> None:
    for message_id, fields in messages:
        raw = fields.get("event") or fields.get(b"event")
        if raw is None:
            await redis_client.xack(key, group, message_id)
            continue
        event = ZeusEvent.from_json(raw)
        await handle_stream_event(
            event,
            message_id=message_id,
            key=key,
            group=group,
            handler=handler,
            session_factory=session_factory,
            redis_client=redis_client,
        )


async def handle_stream_event(
    event: ZeusEvent,
    *,
    message_id: str,
    key: str,
    group: str,
    handler: EventHandler,
    session_factory: async_sessionmaker[AsyncSession] | None,
    redis_client: Redis,
) -> None:
    if session_factory is None:
        try:
            await dispatch_event(event, handler)
        except Exception:
            logger.exception("Event handler failed for channel %s", event.channel)
        await redis_client.xack(key, group, message_id)
        return

    async with session_factory() as session:
        try:
            await dispatch_event(event, handler, session=session)
        except Exception:
            await session.commit()
            await redis_client.xack(key, group, message_id)
            logger.exception("Event handler failed for channel %s", event.channel)
            return

        await session.commit()

        try:
            await publish_pending_events(session, redis_client=redis_client)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Pending event relay failed after handling %s", event.id)

    await redis_client.xack(key, group, message_id)


async def _subscribe_pubsub(
    channel: str,
    handler: EventHandler,
    *,
    redis_client: Redis,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    client = redis_client
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
