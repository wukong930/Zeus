import asyncio
import logging
from collections.abc import Callable

from app.core.database import AsyncSessionLocal
from app.core.events import EventHandler, relay_pending_events, replay_unhandled_events, subscribe
from app.services.pipeline.handlers import (
    handle_market_update,
    handle_news_event,
    handle_signal_detected,
    handle_signal_scored,
)
from app.services.positions.events import handle_position_changed
from app.services.positions.threshold_modifier import refresh_position_threshold_cache

logger = logging.getLogger(__name__)

PIPELINE_SUBSCRIPTIONS: tuple[tuple[str, EventHandler], ...] = (
    ("market.update", handle_market_update),
    ("news.event", handle_news_event),
    ("signal.detected", handle_signal_detected),
    ("signal.scored", handle_signal_scored),
    ("position.changed", handle_position_changed),
)


class EventPipelineRuntime:
    def __init__(
        self,
        subscriptions: tuple[tuple[str, EventHandler], ...] = PIPELINE_SUBSCRIPTIONS,
        subscriber: Callable[..., asyncio.Future | asyncio.Task | object] = subscribe,
    ) -> None:
        self._subscriptions = subscriptions
        self._subscriber = subscriber
        self._stop_event: asyncio.Event | None = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._tasks:
            return

        async with AsyncSessionLocal() as session:
            await refresh_position_threshold_cache(session)

        self._stop_event = asyncio.Event()
        self._tasks.append(
            asyncio.create_task(
                relay_pending_events(
                    session_factory=AsyncSessionLocal,
                    stop_event=self._stop_event,
                )
            )
        )
        for channel, handler in self._subscriptions:
            self._tasks.append(
                asyncio.create_task(
                    self._subscriber(
                        channel,
                        handler,
                        session_factory=AsyncSessionLocal,
                        stop_event=self._stop_event,
                    )
                )
            )
        async with AsyncSessionLocal() as session:
            replayed = await replay_unhandled_events(
                session,
                channels=tuple(channel for channel, _ in self._subscriptions),
            )
        if replayed:
            logger.info("Replayed %s unhandled published event(s)", replayed)
        logger.info("Started %s event pipeline tasks", len(self._tasks))

    async def stop(self) -> None:
        if not self._tasks:
            return

        if self._stop_event is not None:
            self._stop_event.set()
        done, pending = await asyncio.wait(self._tasks, timeout=2)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                logger.warning("Event pipeline task exited with error: %s", exc)
        self._tasks.clear()
        self._stop_event = None


_event_pipeline = EventPipelineRuntime()


def get_event_pipeline() -> EventPipelineRuntime:
    return _event_pipeline
