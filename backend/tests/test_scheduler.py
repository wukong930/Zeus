import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.scheduler.jobs import (
    DEFAULT_JOB_DEFINITIONS,
    DEFAULT_JOB_HANDLERS,
    JobDefinition,
    collect_news_from_collectors,
)
from app.scheduler.manager import SchedulerManager
from app.services.news.collectors import CailiansheCollector, ExchangeAnnouncementsCollector, SinaFuturesCollector
from app.services.news.types import NewsCollectorUnavailable, RawNewsItem


async def _ok_handler() -> dict:
    return {"ok": True}


async def _failing_handler() -> dict:
    raise RuntimeError("boom")


class ApiScheduler:
    def __init__(self, run_result: dict | None = None, *, start_success: bool = True) -> None:
        self.run_result = run_result or {"success": True, "data": {"ok": True}}
        self.start_success = start_success

    def list_jobs(self) -> list[dict]:
        return [{"id": "known", "status": "ok"}]

    def health_summary(self) -> dict:
        return {"total_jobs": 1}

    def start_all(self) -> None:
        return None

    def stop_all(self) -> None:
        return None

    def start_job(self, _job_id: str) -> bool:
        return self.start_success

    def stop_job(self, _job_id: str) -> bool:
        return True

    def update_cron(self, _job_id: str, cron: str) -> bool:
        return cron == "* * * * *"

    async def run_now(self, _job_id: str) -> dict:
        return self.run_result


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


async def test_unwired_news_collectors_report_unavailable_errors() -> None:
    items, errors = await collect_news_from_collectors(
        [CailiansheCollector(), SinaFuturesCollector(), ExchangeAnnouncementsCollector()],
        limit=7,
    )

    assert items == []
    assert [error["source"] for error in errors] == [
        "cailianshe",
        "sina_futures",
        "exchange_announcements",
    ]
    assert all("not connected" in error["error"] for error in errors)


async def test_unwired_collector_raises_explicit_unavailable_error() -> None:
    collector = SinaFuturesCollector()

    try:
        await collector.collect()
    except NewsCollectorUnavailable as exc:
        assert "not connected" in str(exc)
    else:
        raise AssertionError("SinaFuturesCollector should report unavailable runtime feed")


async def test_scheduler_marks_degraded_payload_as_warning() -> None:
    async def _degraded_handler() -> dict:
        return {"status": "degraded", "collector_errors": [{"source": "x", "error": "offline"}]}

    manager = SchedulerManager(
        definitions=(JobDefinition("test", "Test", "* * * * *"),),
        handlers={"test": _degraded_handler},
    )

    result = await manager.run_now("test")

    assert result["success"] is True
    assert manager.list_jobs()[0]["last_result"] == "degraded"
    assert manager.list_jobs()[0]["status"] == "warning"
    assert manager.health_summary()["warning_jobs"] == ["test"]


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
    assert health["warning_jobs"] == []
    assert health["unconfigured_jobs"] == ["planned"]
    assert manager.start_job("planned") is False


def scheduler_api_client(monkeypatch, scheduler: ApiScheduler) -> TestClient:
    monkeypatch.setattr("app.api.scheduler.get_scheduler", lambda: scheduler)
    return TestClient(create_app())


def test_scheduler_api_rejects_unknown_job(monkeypatch) -> None:
    client = scheduler_api_client(monkeypatch, ApiScheduler())

    response = client.post("/api/scheduler", json={"action": "run", "job_id": "missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "scheduler job not found"


def test_scheduler_api_rejects_invalid_cron(monkeypatch) -> None:
    client = scheduler_api_client(monkeypatch, ApiScheduler())

    response = client.post(
        "/api/scheduler",
        json={"action": "updateCron", "job_id": "known", "cron": "not cron"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid cron"


def test_scheduler_api_rejects_unconfigured_manual_run(monkeypatch) -> None:
    client = scheduler_api_client(
        monkeypatch,
        ApiScheduler(run_result={"success": False, "error": "No handler registered for job known"}),
    )

    response = client.post("/api/scheduler", json={"action": "run", "job_id": "known"})

    assert response.status_code == 409
    assert response.json()["detail"] == "scheduler job is not configured"
