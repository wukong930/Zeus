from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.drift_metrics import DriftMetric

router = APIRouter(prefix="/api/drift", tags=["drift"])

DRIFT_SEVERITY_PATTERN = "^(green|yellow|red)$"
MAX_DRIFT_FILTER_LENGTH = 40


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


class DriftNotificationRead(BaseModel):
    level: str
    title: str
    summary: str
    should_notify: bool
    production_effect: str
    channels: list[str]
    next_actions: list[str]
    top_metrics: list[DriftMetricRead]


class DriftSnapshotRead(BaseModel):
    generated_at: datetime
    latest_at: datetime | None
    status: str
    severity_counts: dict[str, int]
    notification: DriftNotificationRead
    metrics: list[DriftMetricRead]


@router.get("/metrics", response_model=DriftSnapshotRead)
async def list_drift_metrics(
    metric_type: str | None = Query(default=None, min_length=1, max_length=MAX_DRIFT_FILTER_LENGTH),
    category: str | None = Query(default=None, min_length=1, max_length=MAX_DRIFT_FILTER_LENGTH),
    drift_severity: str | None = Query(default=None, pattern=DRIFT_SEVERITY_PATTERN),
    before: datetime | None = Query(default=None),
    before_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> DriftSnapshotRead:
    statement = _drift_metrics_statement(
        metric_type=metric_type,
        category=category,
        drift_severity=drift_severity,
        before=before,
        before_id=before_id,
        limit=limit,
    )
    rows = list((await session.scalars(statement)).all())
    return build_drift_snapshot(rows)


def _drift_metrics_statement(
    *,
    metric_type: str | None,
    category: str | None,
    drift_severity: str | None,
    before: datetime | None,
    limit: int,
    before_id: UUID | None = None,
):
    statement = select(DriftMetric).order_by(
        DriftMetric.computed_at.desc(),
        DriftMetric.id.desc(),
    )
    if metric_type is not None:
        statement = statement.where(DriftMetric.metric_type == metric_type)
    if category is not None:
        statement = statement.where(DriftMetric.category == category)
    if drift_severity is not None:
        statement = statement.where(DriftMetric.drift_severity == drift_severity)
    if before is not None:
        if before_id is not None:
            statement = statement.where(
                or_(
                    DriftMetric.computed_at < before,
                    and_(
                        DriftMetric.computed_at == before,
                        DriftMetric.id < before_id,
                    ),
                )
            )
        else:
            statement = statement.where(DriftMetric.computed_at < before)
    return statement.limit(limit)


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
        notification=build_drift_notification(rows, status=status),
        metrics=[drift_metric_to_read(row) for row in rows],
    )


def build_drift_notification(rows: list[DriftMetric], *, status: str) -> DriftNotificationRead:
    top_rows = sorted(
        [row for row in rows if row.drift_severity in {"red", "yellow"}],
        key=lambda row: (_severity_rank(row.drift_severity), row.psi or 0, row.computed_at),
        reverse=True,
    )[:5]
    if status == "red":
        return DriftNotificationRead(
            level="review",
            title="严重 Drift 告警",
            summary="市场结构已明显偏离校准样本，需人工复核信号权重和阈值表现。",
            should_notify=True,
            production_effect="observe_only",
            channels=["heartbeat", "analytics_drift", "notification_settings"],
            next_actions=[
                "打开 Analytics / Drift 监控查看红色指标",
                "复核相关 signal_type / category 的近期命中率",
                "在人工审批前保持生产阈值不变",
            ],
            top_metrics=[drift_metric_to_read(row) for row in top_rows],
        )
    if status == "yellow":
        return DriftNotificationRead(
            level="watch",
            title="Drift 关注提示",
            summary="部分指标出现黄色漂移，建议观察下一轮调度结果，不自动修改生产阈值。",
            should_notify=True,
            production_effect="observe_only",
            channels=["heartbeat", "analytics_drift"],
            next_actions=[
                "观察黄色指标是否连续出现",
                "检查数据源新鲜度和样本量",
                "必要时进入治理队列再调整校准参数",
            ],
            top_metrics=[drift_metric_to_read(row) for row in top_rows],
        )
    if status == "green":
        return DriftNotificationRead(
            level="none",
            title="Drift 正常",
            summary="当前市场结构与校准样本保持一致，无需通知。",
            should_notify=False,
            production_effect="observe_only",
            channels=["heartbeat", "analytics_drift"],
            next_actions=["保持监控，不自动修改生产阈值"],
            top_metrics=[],
        )
    return DriftNotificationRead(
        level="no_data",
        title="暂无 Drift 数据",
        summary="调度器尚未写入 Drift 指标，等待下一轮监控任务。",
        should_notify=False,
        production_effect="observe_only",
        channels=["analytics_drift"],
        next_actions=["确认 drift-monitor 调度任务是否启用"],
        top_metrics=[],
    )


def drift_metric_to_read(row: DriftMetric) -> DriftMetricRead:
    return DriftMetricRead(
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


def _severity_rank(severity: str) -> int:
    if severity == "red":
        return 3
    if severity == "yellow":
        return 2
    if severity == "green":
        return 1
    return 0
