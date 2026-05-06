from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.drift_metrics import DriftMetric

router = APIRouter(prefix="/api/drift", tags=["drift"])


class DriftMetricRead(BaseModel):
    id: UUID
    metric_type: str
    category: str | None
    feature_name: str | None
    current_value: float | None
    baseline_value: float | None
    psi: float | None
    drift_severity: str
    details: dict[str, Any]
    computed_at: datetime


class DriftSnapshotRead(BaseModel):
    generated_at: datetime
    latest_at: datetime | None
    status: str
    severity_counts: dict[str, int]
    metrics: list[DriftMetricRead]


@router.get("/metrics", response_model=DriftSnapshotRead)
async def list_drift_metrics(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> DriftSnapshotRead:
    statement = select(DriftMetric).order_by(DriftMetric.computed_at.desc()).limit(limit)
    rows = list((await session.scalars(statement)).all())
    return build_drift_snapshot(rows)


def build_drift_snapshot(rows: list[DriftMetric]) -> DriftSnapshotRead:
    severity_counts = {"green": 0, "yellow": 0, "red": 0}
    latest_at: datetime | None = None
    for row in rows:
        severity_counts[row.drift_severity] = severity_counts.get(row.drift_severity, 0) + 1
        if latest_at is None or row.computed_at > latest_at:
            latest_at = row.computed_at

    status = "no_data"
    if severity_counts.get("red", 0) > 0:
        status = "red"
    elif severity_counts.get("yellow", 0) > 0:
        status = "yellow"
    elif rows:
        status = "green"

    return DriftSnapshotRead(
        generated_at=datetime.now(timezone.utc),
        latest_at=latest_at,
        status=status,
        severity_counts=severity_counts,
        metrics=[
            DriftMetricRead(
                id=row.id,
                metric_type=row.metric_type,
                category=row.category,
                feature_name=row.feature_name,
                current_value=row.current_value,
                baseline_value=row.baseline_value,
                psi=row.psi,
                drift_severity=row.drift_severity,
                details=row.details,
                computed_at=row.computed_at,
            )
            for row in rows
        ],
    )
