from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.shadow_runs import ShadowRun
from app.models.shadow_signals import ShadowSignal
from app.services.calibration.threshold_calibrator import (
    enqueue_threshold_review,
    generate_threshold_calibration_report,
)
from app.services.shadow.comparator import compare_shadow_run
from app.services.shadow.runner import create_shadow_run, stop_shadow_run

router = APIRouter(prefix="/api/shadow", tags=["shadow"])


class ShadowRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    algorithm_version: str = Field(min_length=1, max_length=80)
    config_diff: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    notes: str | None = None


@router.get("/runs")
async def list_shadow_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(ShadowRun).order_by(ShadowRun.started_at.desc()).limit(limit)
        )
    ).all()
    return [shadow_run_to_dict(row) for row in rows]


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_shadow_run_endpoint(
    payload: ShadowRunCreate,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await create_shadow_run(
        session,
        name=payload.name,
        algorithm_version=payload.algorithm_version,
        config_diff=payload.config_diff,
        created_by=payload.created_by,
        notes=payload.notes,
    )
    await session.commit()
    await session.refresh(row)
    return shadow_run_to_dict(row)


@router.post("/runs/{run_id}/stop")
async def stop_shadow_run_endpoint(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await stop_shadow_run(session, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    await session.commit()
    await session.refresh(row)
    return shadow_run_to_dict(row)


@router.get("/runs/{run_id}/report")
async def get_shadow_run_report(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await compare_shadow_run(session, run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    signal_count = await _shadow_signal_count(session, run_id)
    payload = report.to_dict()
    payload["shadow_signal_rows"] = signal_count
    return payload


@router.get("/calibration")
async def get_threshold_calibration_report(
    signal_type: str | None = None,
    category: str | None = None,
    lookback_days: int = Query(default=180, ge=7, le=730),
    min_samples: int = Query(default=20, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await generate_threshold_calibration_report(
        session,
        signal_type=signal_type,
        category=category,
        lookback_days=lookback_days,
        min_samples=min_samples,
    )
    return report.to_dict()


@router.post("/calibration/reviews")
async def enqueue_threshold_calibration_review(
    signal_type: str | None = None,
    category: str | None = None,
    lookback_days: int = Query(default=180, ge=7, le=730),
    min_samples: int = Query(default=20, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    report = await generate_threshold_calibration_report(
        session,
        signal_type=signal_type,
        category=category,
        lookback_days=lookback_days,
        min_samples=min_samples,
    )
    if not report.review_required:
        return {"queued": False, "report": report.to_dict()}
    row = await enqueue_threshold_review(session, report)
    await session.commit()
    return {
        "queued": True,
        "review_id": str(row.id),
        "target_key": row.target_key,
        "report": report.to_dict(),
    }


async def _shadow_signal_count(session: AsyncSession, run_id: UUID) -> int:
    rows = (
        await session.scalars(
            select(ShadowSignal).where(ShadowSignal.shadow_run_id == run_id)
        )
    ).all()
    return len(rows)


def shadow_run_to_dict(row: ShadowRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "algorithm_version": row.algorithm_version,
        "config_diff": row.config_diff,
        "status": row.status,
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
        "created_by": row.created_by,
        "notes": row.notes,
        "created_at": _iso(row.created_at),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
