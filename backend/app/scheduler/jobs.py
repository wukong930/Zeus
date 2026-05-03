from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.database import AsyncSessionLocal
from app.core.events import publish
from app.services.calibration.shadow_tracker import evaluate_pending_signals
from app.services.signals.watchlist import get_enabled_watchlist


JobHandler = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class JobDefinition:
    id: str
    name: str
    cron: str
    enabled: bool = True


DEFAULT_JOB_DEFINITIONS: tuple[JobDefinition, ...] = (
    JobDefinition("ingest", "行情数据", "5 10,11,14,15 * * 1-5"),
    JobDefinition("context", "上下文刷新", "0 */4 * * *"),
    JobDefinition("alerts", "预警触发", "0 * * * *"),
    JobDefinition("evolution", "假设演化", "0 8 * * *"),
    JobDefinition("risk", "风险计算", "30 8 * * *"),
    JobDefinition("auto-eval", "信号评判", "0 9 * * *"),
    JobDefinition("track-outcomes", "绩效追踪", "30 16 * * 1-5"),
    JobDefinition("calibration", "校准更新", "0 2 * * *"),
    JobDefinition("regime-detect", "Regime 检测", "20 16 * * 1-5"),
    JobDefinition("drift-monitor", "漂移监控", "40 16 * * 1-5"),
    JobDefinition("cleanup", "数据清理", "0 3 * * *"),
    JobDefinition("main-contract", "主力合约日检", "10 16 * * 1-5"),
)


async def placeholder_job() -> dict[str, Any]:
    return {
        "status": "noop",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def ingest_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        watchlist = await get_enabled_watchlist(session)
        event = await publish(
            "market.update",
            {
                "job_id": "ingest",
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "status": "ready",
                "watchlist_count": len(watchlist),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "published",
        "event_id": str(event.id),
        "channel": event.channel,
        "timestamp": event.timestamp.isoformat(),
    }


async def publish_job_event(job_id: str, channel: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        event = await publish(
            channel,
            {
                "job_id": job_id,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "status": "requested",
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "published",
        "event_id": str(event.id),
        "channel": event.channel,
        "timestamp": event.timestamp.isoformat(),
    }


async def calibration_job() -> dict[str, Any]:
    return await publish_job_event("calibration", "calibration.run_requested")


async def track_outcomes_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await evaluate_pending_signals(session)
        await session.commit()
    return {
        "status": "completed",
        "scanned": result.scanned,
        "resolved": result.resolved,
        "pending": result.pending,
        "skipped": result.skipped,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def regime_detection_job() -> dict[str, Any]:
    return await publish_job_event("regime-detect", "regime.detect_requested")


async def drift_monitor_job() -> dict[str, Any]:
    return await publish_job_event("drift-monitor", "drift.check_requested")


DEFAULT_JOB_HANDLERS: dict[str, JobHandler] = {
    definition.id: placeholder_job for definition in DEFAULT_JOB_DEFINITIONS
}
DEFAULT_JOB_HANDLERS["ingest"] = ingest_job
DEFAULT_JOB_HANDLERS["track-outcomes"] = track_outcomes_job
DEFAULT_JOB_HANDLERS["calibration"] = calibration_job
DEFAULT_JOB_HANDLERS["regime-detect"] = regime_detection_job
DEFAULT_JOB_HANDLERS["drift-monitor"] = drift_monitor_job
