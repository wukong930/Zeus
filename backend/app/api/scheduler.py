from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from app.schemas.common import StrictInputModel
from app.scheduler.manager import get_scheduler

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

MAX_SCHEDULER_JOB_ID_LENGTH = 80
MAX_SCHEDULER_CRON_LENGTH = 120


class SchedulerAction(StrictInputModel):
    action: Literal["start", "stop", "run", "updateCron", "startAll", "stopAll"]
    job_id: str | None = Field(default=None, min_length=1, max_length=MAX_SCHEDULER_JOB_ID_LENGTH)
    cron: str | None = Field(default=None, min_length=1, max_length=MAX_SCHEDULER_CRON_LENGTH)

    @field_validator("job_id", "cron")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("scheduler text fields must be non-empty")
        return trimmed


@router.get("")
async def list_scheduler_jobs() -> dict:
    scheduler = get_scheduler()
    return {
        "jobs": scheduler.list_jobs(),
        "health": scheduler.health_summary(),
    }


@router.post("")
async def mutate_scheduler(payload: SchedulerAction) -> dict:
    scheduler = get_scheduler()

    if payload.action == "startAll":
        scheduler.start_all()
        return {"success": True}
    if payload.action == "stopAll":
        scheduler.stop_all()
        return {"success": True}

    if payload.job_id is None:
        raise HTTPException(status_code=400, detail="job_id is required")
    if not scheduler_job_exists(scheduler, payload.job_id):
        raise HTTPException(status_code=404, detail="scheduler job not found")

    if payload.action == "start":
        if not scheduler.start_job(payload.job_id):
            raise HTTPException(status_code=409, detail="scheduler job is not configured")
        return {"success": True}
    if payload.action == "stop":
        if not scheduler.stop_job(payload.job_id):
            raise HTTPException(status_code=404, detail="scheduler job not found")
        return {"success": True}
    if payload.action == "run":
        return scheduler_run_response(await scheduler.run_now(payload.job_id))
    if payload.action == "updateCron":
        if payload.cron is None:
            raise HTTPException(status_code=400, detail="cron is required")
        if not scheduler.update_cron(payload.job_id, payload.cron):
            raise HTTPException(status_code=400, detail="invalid cron")
        return {"success": True}

    raise HTTPException(status_code=400, detail="Unknown action")


def scheduler_job_exists(scheduler, job_id: str) -> bool:
    return any(job.get("id") == job_id for job in scheduler.list_jobs())


def scheduler_run_response(result: dict) -> dict:
    if result.get("success") is True:
        return result
    error = str(result.get("error") or "scheduler run failed")
    if error == "unknown job":
        raise HTTPException(status_code=404, detail="scheduler job not found")
    if error == "busy":
        raise HTTPException(status_code=409, detail="scheduler job is already running")
    if error.startswith("No handler registered"):
        raise HTTPException(status_code=409, detail="scheduler job is not configured")
    raise HTTPException(status_code=500, detail=error)
