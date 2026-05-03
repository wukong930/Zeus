from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.database import AsyncSessionLocal
from app.core.events import publish
from app.services.adversarial.null_hypothesis import precompute_all_null_distributions
from app.services.calibration.regime_batch import detect_and_record_all_regimes
from app.services.calibration.shadow_tracker import evaluate_pending_signals
from app.services.calibration.updater import generate_calibration_reviews
from app.services.contracts.main_contract_batch import detect_and_apply_main_contracts
from app.services.learning.drift_monitor import run_drift_monitor
from app.services.news.collectors import (
    CailiansheCollector,
    ExchangeAnnouncementsCollector,
    SinaFuturesCollector,
)
from app.services.news.ingest import ingest_news_items
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
    JobDefinition("adversarial-cache", "对抗零分布", "25 16 * * 1-5"),
    JobDefinition("news-ingest", "新闻事件采集", "*/30 * * * *"),
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


async def calibration_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await generate_calibration_reviews(session)
        event = await publish(
            "calibration.review_queued",
            {
                "job_id": "calibration",
                "groups": result.groups,
                "queued": result.queued,
                "skipped": result.skipped,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "completed",
        "event_id": str(event.id),
        "channel": event.channel,
        "groups": result.groups,
        "queued": result.queued,
        "skipped": result.skipped,
        "timestamp": event.timestamp.isoformat(),
    }


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
    async with AsyncSessionLocal() as session:
        result = await detect_and_record_all_regimes(session)
        event = await publish(
            "regime.detected",
            {
                "job_id": "regime-detect",
                "categories": result.categories,
                "recorded": result.recorded,
                "skipped": result.skipped,
                "as_of_date": result.as_of_date.isoformat(),
                "details": result.details,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "completed",
        "event_id": str(event.id),
        "channel": event.channel,
        "categories": result.categories,
        "recorded": result.recorded,
        "skipped": result.skipped,
        "timestamp": event.timestamp.isoformat(),
    }


async def drift_monitor_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await run_drift_monitor(session)
        event = await publish(
            "drift.metrics_recorded",
            {
                "job_id": "drift-monitor",
                "categories": result.categories,
                "recorded": result.recorded,
                "skipped": result.skipped,
                "details": result.details,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "completed",
        "event_id": str(event.id),
        "channel": event.channel,
        "categories": result.categories,
        "recorded": result.recorded,
        "skipped": result.skipped,
        "timestamp": event.timestamp.isoformat(),
    }


async def main_contract_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await detect_and_apply_main_contracts(session)
        event = await publish(
            "contract.main_checked",
            {
                "job_id": "main-contract",
                "symbols": result.symbols,
                "updated": result.updated,
                "skipped": result.skipped,
                "details": result.details,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "completed",
        "event_id": str(event.id),
        "channel": event.channel,
        "symbols": result.symbols,
        "updated": result.updated,
        "skipped": result.skipped,
        "timestamp": event.timestamp.isoformat(),
    }


async def adversarial_cache_job() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        rows = await precompute_all_null_distributions(session)
        event = await publish(
            "adversarial.cache_updated",
            {
                "job_id": "adversarial-cache",
                "updated": len(rows),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            },
            source="scheduler",
            session=session,
        )
        await session.commit()
    return {
        "status": "completed",
        "event_id": str(event.id),
        "channel": event.channel,
        "updated": len(rows),
        "timestamp": event.timestamp.isoformat(),
    }


async def news_ingest_job() -> dict[str, Any]:
    collectors = (
        CailiansheCollector(),
        SinaFuturesCollector(),
        ExchangeAnnouncementsCollector(),
    )
    raw_items = []
    for collector in collectors:
        raw_items.extend(await collector.collect(limit=50))

    async with AsyncSessionLocal() as session:
        result = await ingest_news_items(session, raw_items)
        await session.commit()
    return {
        "status": "completed",
        "collected": result.collected,
        "recorded": result.recorded,
        "duplicates": result.duplicates,
        "published": result.published,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


DEFAULT_JOB_HANDLERS: dict[str, JobHandler] = {
    definition.id: placeholder_job for definition in DEFAULT_JOB_DEFINITIONS
}
DEFAULT_JOB_HANDLERS["ingest"] = ingest_job
DEFAULT_JOB_HANDLERS["track-outcomes"] = track_outcomes_job
DEFAULT_JOB_HANDLERS["calibration"] = calibration_job
DEFAULT_JOB_HANDLERS["regime-detect"] = regime_detection_job
DEFAULT_JOB_HANDLERS["drift-monitor"] = drift_monitor_job
DEFAULT_JOB_HANDLERS["main-contract"] = main_contract_job
DEFAULT_JOB_HANDLERS["adversarial-cache"] = adversarial_cache_job
DEFAULT_JOB_HANDLERS["news-ingest"] = news_ingest_job
