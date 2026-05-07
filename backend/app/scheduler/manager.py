import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.jobs import DEFAULT_JOB_DEFINITIONS, DEFAULT_JOB_HANDLERS, JobDefinition, JobHandler


@dataclass
class ScheduledJobState:
    id: str
    name: str
    cron: str
    enabled: bool
    running: bool = False
    last_run: datetime | None = None
    last_result: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0

    def status(self, *, handler_registered: bool = True) -> str:
        if not handler_registered:
            return "unconfigured"
        if not self.enabled:
            return "disabled"
        if self.consecutive_failures >= 3:
            return "degraded"
        if self.last_result in {"degraded", "skipped"}:
            return "warning"
        if self.last_result == "error":
            return "warning"
        return "ok"

    def to_dict(self, *, handler_registered: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status(handler_registered=handler_registered)
        if self.last_run is not None:
            data["last_run"] = self.last_run.isoformat()
        return data


class SchedulerManager:
    def __init__(
        self,
        definitions: tuple[JobDefinition, ...] = DEFAULT_JOB_DEFINITIONS,
        handlers: dict[str, JobHandler] | None = None,
    ) -> None:
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._handlers = handlers or DEFAULT_JOB_HANDLERS
        self._jobs: dict[str, ScheduledJobState] = {
            definition.id: ScheduledJobState(
                id=definition.id,
                name=definition.name,
                cron=definition.cron,
                enabled=definition.enabled,
            )
            for definition in definitions
        }
        self._lock = asyncio.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        self._scheduler.start(paused=False)
        self._started = True
        for job_id, state in self._jobs.items():
            if state.enabled:
                self.start_job(job_id)

    def shutdown(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            job.to_dict(handler_registered=job.id in self._handlers)
            for job in self._jobs.values()
        ]

    def health_summary(self) -> dict[str, Any]:
        jobs = list(self._jobs.values())
        last_runs = [job.last_run for job in jobs if job.last_run is not None]
        last_activity = max(last_runs).isoformat() if last_runs else None
        statuses = {
            job.id: job.status(handler_registered=job.id in self._handlers)
            for job in jobs
        }
        return {
            "total_jobs": len(jobs),
            "enabled_jobs": sum(1 for job in jobs if job.enabled and job.id in self._handlers),
            "degraded_jobs": [job.id for job in jobs if statuses[job.id] == "degraded"],
            "warning_jobs": [job.id for job in jobs if statuses[job.id] == "warning"],
            "unconfigured_jobs": [job.id for job in jobs if statuses[job.id] == "unconfigured"],
            "last_activity": last_activity,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "status": statuses[job.id],
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "last_error": job.last_error if job.consecutive_failures > 0 else None,
                }
                for job in jobs
            ],
        }

    def start_job(self, job_id: str) -> bool:
        state = self._jobs.get(job_id)
        if state is None:
            return False
        if job_id not in self._handlers:
            state.enabled = False
            state.last_result = "error"
            state.last_error = f"No handler registered for job {job_id}"
            return False

        trigger = CronTrigger.from_crontab(state.cron, timezone="Asia/Shanghai")
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)
        self._scheduler.add_job(
            self.run_now,
            trigger=trigger,
            args=[job_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        state.enabled = True
        return True

    def stop_job(self, job_id: str) -> bool:
        state = self._jobs.get(job_id)
        if state is None:
            return False
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)
        state.enabled = False
        return True

    def start_all(self) -> None:
        for job_id in self._jobs:
            self.start_job(job_id)

    def stop_all(self) -> None:
        for job_id in self._jobs:
            self.stop_job(job_id)

    def update_cron(self, job_id: str, cron: str) -> bool:
        state = self._jobs.get(job_id)
        if state is None:
            return False
        try:
            CronTrigger.from_crontab(cron, timezone="Asia/Shanghai")
        except ValueError:
            return False

        state.cron = cron
        if state.enabled:
            self.start_job(job_id)
        return True

    async def run_now(self, job_id: str) -> dict[str, Any]:
        state = self._jobs.get(job_id)
        if state is None:
            return {"success": False, "error": "unknown job"}

        async with self._lock:
            if state.running:
                return {"success": False, "error": "busy"}
            state.running = True

        try:
            handler = self._handlers.get(job_id)
            if handler is None:
                raise RuntimeError(f"No handler registered for job {job_id}")

            payload = await handler()
            state.last_run = datetime.now(timezone.utc)
            state.last_result = job_result_status(payload)
            state.last_error = None
            state.consecutive_failures = 0
            return {"success": True, "data": payload}
        except Exception as exc:
            state.last_run = datetime.now(timezone.utc)
            state.last_result = "error"
            state.last_error = str(exc)
            state.consecutive_failures += 1
            return {"success": False, "error": str(exc)}
        finally:
            state.running = False


_scheduler = SchedulerManager()


def get_scheduler() -> SchedulerManager:
    return _scheduler


def job_result_status(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status in {"degraded", "skipped"}:
        return str(status)
    return "success"
