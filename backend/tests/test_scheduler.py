import asyncio
from datetime import datetime, timezone

from app.scheduler.jobs import (
    DEFAULT_JOB_DEFINITIONS,
    DEFAULT_JOB_HANDLERS,
    JobDefinition,
    collect_news_from_collectors,
)
from app.scheduler.manager import SchedulerManager
from app.services.news.types import RawNewsItem


async def _ok_handler() -> dict:
    return {"ok": True}


async def _failing_handler() -> dict:
    raise RuntimeError("boom")


def test_scheduler_lists_default_jobs() -> None:
    manager = SchedulerManager(
        definitions=(JobDefinition("test", "Test", "* * * * *"),),
        handlers={"test": _ok_handler},
    )

    jobs = manager.list_jobs()

    assert jobs[0]["id"] == "test"
    assert jobs[0]["status"] == "ok"


async def test_scheduler_run_now_tracks_success() -> None:
    manager = SchedulerManager(
        definitions=(JobDefinition("test", "Test", "* * * * *"),),
        handlers={"test": _ok_handler},
    )

    result = await manager.run_now("test")

    assert result["success"] is True
    assert manager.health_summary()["jobs"][0]["status"] == "ok"


async def test_scheduler_marks_degraded_after_three_failures() -> None:
    manager = SchedulerManager(
        definitions=(JobDefinition("test", "Test", "* * * * *"),),
        handlers={"test": _failing_handler},
    )

    for _ in range(3):
        result = await manager.run_now("test")

    assert result["success"] is False
    assert manager.health_summary()["degraded_jobs"] == ["test"]


async def test_news_collectors_run_concurrently_and_keep_source_errors() -> None:
    gate = asyncio.Event()
    started = asyncio.Event()

    class WaitingCollector:
        source = "waiting"

        async def collect(self, limit: int = 50) -> list[RawNewsItem]:
            started.set()
            await gate.wait()
            return [
                RawNewsItem(
                    source=self.source,
                    title=f"waiting {limit}",
                    published_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
                )
            ]

    class ReleasingCollector:
        source = "releasing"

        async def collect(self, limit: int = 50) -> list[RawNewsItem]:
            await started.wait()
            gate.set()
            return [
                RawNewsItem(
                    source=self.source,
                    title=f"releasing {limit}",
                    published_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
                )
            ]

    class FailingCollector:
        source = "failing"

        async def collect(self, limit: int = 50) -> list[RawNewsItem]:
            raise RuntimeError(f"failed at {limit}")

    items, errors = await asyncio.wait_for(
        collect_news_from_collectors(
            [WaitingCollector(), ReleasingCollector(), FailingCollector()],
            limit=7,
        ),
        timeout=0.2,
    )

    assert [item.source for item in items] == ["waiting", "releasing"]
    assert [item.title for item in items] == ["waiting 7", "releasing 7"]
    assert errors == [{"source": "failing", "error": "failed at 7"}]


def test_scheduler_rejects_bad_cron() -> None:
    manager = SchedulerManager(
        definitions=(JobDefinition("test", "Test", "* * * * *"),),
        handlers={"test": _ok_handler},
    )

    assert manager.update_cron("test", "not cron") is False


def test_cost_snapshots_job_is_registered() -> None:
    assert any(definition.id == "cost-snapshots" for definition in DEFAULT_JOB_DEFINITIONS)
    assert DEFAULT_JOB_HANDLERS["cost-snapshots"].__name__ == "cost_snapshots_job"


def test_rubber_cost_snapshots_job_is_registered() -> None:
    assert any(definition.id == "rubber-cost-snapshots" for definition in DEFAULT_JOB_DEFINITIONS)
    assert DEFAULT_JOB_HANDLERS["rubber-cost-snapshots"].__name__ == "rubber_cost_snapshots_job"


def test_default_jobs_are_registered_or_explicitly_unconfigured() -> None:
    for definition in DEFAULT_JOB_DEFINITIONS:
        assert definition.id in DEFAULT_JOB_HANDLERS or definition.enabled is False


def test_scheduler_reports_missing_handlers_as_unconfigured() -> None:
    manager = SchedulerManager(
        definitions=(JobDefinition("planned", "Planned", "* * * * *", enabled=False),),
        handlers={},
    )

    jobs = manager.list_jobs()
    health = manager.health_summary()

    assert jobs[0]["status"] == "unconfigured"
    assert health["enabled_jobs"] == 0
    assert health["unconfigured_jobs"] == ["planned"]
    assert manager.start_job("planned") is False
