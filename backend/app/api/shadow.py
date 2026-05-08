import json
import math
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.shadow_runs import ShadowRun
from app.models.shadow_signals import ShadowSignal
from app.schemas.common import StrictInputModel
from app.services.calibration.threshold_calibrator import (
    enqueue_threshold_review,
    generate_threshold_calibration_report,
)
from app.services.shadow.applications import (
    create_initial_shadow_applications,
    initial_shadow_application_specs,
)
from app.services.shadow.comparator import compare_shadow_run
from app.services.shadow.runner import create_shadow_run, stop_shadow_run

router = APIRouter(prefix="/api/shadow", tags=["shadow"])

MAX_SHADOW_CONFIG_TOP_LEVEL_KEYS = 32
MAX_SHADOW_CONFIG_OBJECT_KEYS = 64
MAX_SHADOW_CONFIG_LIST_ITEMS = 80
MAX_SHADOW_CONFIG_DEPTH = 6
MAX_SHADOW_CONFIG_NODES = 300
MAX_SHADOW_CONFIG_BYTES = 16_384
MAX_SHADOW_CONFIG_KEY_LENGTH = 80
MAX_SHADOW_CONFIG_STRING_LENGTH = 500
MAX_SHADOW_ACTOR_LENGTH = 80
MAX_SHADOW_SIGNAL_TYPE_LENGTH = 30
MAX_SHADOW_CATEGORY_LENGTH = 30


class ShadowRunCreate(StrictInputModel):
    name: str = Field(min_length=1, max_length=120)
    algorithm_version: str = Field(min_length=1, max_length=80)
    config_diff: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_SHADOW_CONFIG_TOP_LEVEL_KEYS,
    )
    created_by: str | None = Field(default=None, max_length=MAX_SHADOW_ACTOR_LENGTH)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("config_diff")
    @classmethod
    def validate_config_diff(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_config_shape(value)
        try:
            encoded = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("config_diff must be JSON serializable") from exc
        if len(encoded.encode("utf-8")) > MAX_SHADOW_CONFIG_BYTES:
            raise ValueError(f"config_diff must be at most {MAX_SHADOW_CONFIG_BYTES} bytes")
        return value


def _validate_json_config_shape(value: Any, *, depth: int = 0, nodes: int = 0) -> int:
    if depth > MAX_SHADOW_CONFIG_DEPTH:
        raise ValueError(f"config_diff nesting cannot exceed {MAX_SHADOW_CONFIG_DEPTH} levels")
    nodes += 1
    if nodes > MAX_SHADOW_CONFIG_NODES:
        raise ValueError(f"config_diff can include at most {MAX_SHADOW_CONFIG_NODES} nodes")
    if isinstance(value, dict):
        if len(value) > MAX_SHADOW_CONFIG_OBJECT_KEYS:
            raise ValueError(
                f"config_diff objects can include at most {MAX_SHADOW_CONFIG_OBJECT_KEYS} keys"
            )
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("config_diff keys must be non-empty strings")
            if len(key) > MAX_SHADOW_CONFIG_KEY_LENGTH:
                raise ValueError(
                    f"config_diff keys can be at most {MAX_SHADOW_CONFIG_KEY_LENGTH} characters"
                )
            nodes = _validate_json_config_shape(item, depth=depth + 1, nodes=nodes)
        return nodes
    if isinstance(value, list):
        if len(value) > MAX_SHADOW_CONFIG_LIST_ITEMS:
            raise ValueError(
                f"config_diff lists can include at most {MAX_SHADOW_CONFIG_LIST_ITEMS} items"
            )
        for item in value:
            nodes = _validate_json_config_shape(item, depth=depth + 1, nodes=nodes)
        return nodes
    if isinstance(value, str):
        if len(value) > MAX_SHADOW_CONFIG_STRING_LENGTH:
            raise ValueError(
                f"config_diff strings can be at most {MAX_SHADOW_CONFIG_STRING_LENGTH} characters"
            )
        return nodes
    if value is None or isinstance(value, (bool, int)):
        return nodes
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("config_diff numeric values must be finite")
        return nodes
    raise ValueError("config_diff values must be JSON primitives, objects, or lists")


@router.get("/applications/initial")
async def list_initial_shadow_applications() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in initial_shadow_application_specs()]


@router.post("/applications/initial", status_code=status.HTTP_201_CREATED)
async def create_initial_shadow_applications_endpoint(
    created_by: str | None = Query(default=None, min_length=1, max_length=MAX_SHADOW_ACTOR_LENGTH),
    days: int = Query(default=30, ge=1, le=120),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = await create_initial_shadow_applications(
        session,
        created_by=created_by,
        days=days,
    )
    await session.commit()
    return [shadow_run_to_dict(row) for row in rows]


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
    signal_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=MAX_SHADOW_SIGNAL_TYPE_LENGTH,
    ),
    category: str | None = Query(default=None, min_length=1, max_length=MAX_SHADOW_CATEGORY_LENGTH),
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
    signal_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=MAX_SHADOW_SIGNAL_TYPE_LENGTH,
    ),
    category: str | None = Query(default=None, min_length=1, max_length=MAX_SHADOW_CATEGORY_LENGTH),
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
