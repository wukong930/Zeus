import asyncio
import logging
from collections.abc import Callable

from app.core.database import AsyncSessionLocal
from app.core.events import EventHandler, subscribe
from app.services.pipeline.handlers import (
    handle_market_update,
    handle_news_event,
    handle_signal_detected,
    handle_signal_scored,
)
from app.services.positions.events import handle_position_changed

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

    def start(self) -> None:
        if self._tasks:
            return

        self._stop_event = asyncio.Event()
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
        logger.info("Started %s event pipeline subscriptions", len(self._tasks))

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
