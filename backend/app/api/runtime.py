from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.drift import DriftSnapshotRead, build_drift_snapshot
from app.core.database import get_db
from app.models.drift_metrics import DriftMetric
from app.models.signal import SignalTrack
from app.scheduler.manager import get_scheduler
from app.services.calibration.updater import RESOLVED_OUTCOMES

router = APIRouter(prefix="/api/runtime", tags=["runtime"])

ACTIVE_SIGNAL_FRESHNESS_HOURS = 46.8
DEFAULT_DRIFT_LIMIT = 100
DEFAULT_CALIBRATION_LOOKBACK_DAYS = 180
RUNTIME_HEARTBEAT_CACHE_TTL_SECONDS = 10
RUNTIME_HEARTBEAT_CACHE_MAX_ENTRIES = 16

RuntimeHeartbeatCacheKey = tuple[int]
_RUNTIME_HEARTBEAT_CACHE: dict[RuntimeHeartbeatCacheKey, tuple[datetime, RuntimeHeartbeatSnapshot]] = {}


class RuntimeDriftNotification(BaseModel):
    level: str
    title: str
    should_notify: bool


class RuntimeDriftSnapshot(BaseModel):
    status: str
    latest_at: datetime | None
    notification: RuntimeDriftNotification


class RuntimeCalibrationSnapshot(BaseModel):
    samples: int
    lookback_days: int


class RuntimeSchedulerSnapshot(BaseModel):
    degraded_jobs: list[str]
    warning_jobs: list[str]
    unconfigured_jobs: list[str]
    last_activity: str | None
    handler_coverage: dict[str, int]


class RuntimeHeartbeatSnapshot(BaseModel):
    generated_at: datetime
    latest_at: datetime | None
    active_signals: int
    drift: RuntimeDriftSnapshot
    calibration: RuntimeCalibrationSnapshot
    scheduler: RuntimeSchedulerSnapshot
    status: Literal["running", "scheduler_degraded"]


@router.get("/heartbeat", response_model=RuntimeHeartbeatSnapshot)
async def get_runtime_heartbeat(
    calibration_lookback_days: int = Query(
        default=DEFAULT_CALIBRATION_LOOKBACK_DAYS,
        ge=7,
        le=730,
    ),
    refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> RuntimeHeartbeatSnapshot:
    cache_key = _runtime_heartbeat_cache_key(calibration_lookback_days=calibration_lookback_days)
    if not refresh:
        cached = _runtime_heartbeat_cache_get(cache_key)
        if cached is not None:
            return cached

    snapshot = await build_runtime_heartbeat(
        session,
        calibration_lookback_days=calibration_lookback_days,
    )
    _runtime_heartbeat_cache_set(cache_key, snapshot)
    return snapshot


async def build_runtime_heartbeat(
    session: AsyncSession,
    *,
    calibration_lookback_days: int = DEFAULT_CALIBRATION_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> RuntimeHeartbeatSnapshot:
    generated_at = now or datetime.now(timezone.utc)
    active_signals, latest_signal_at = await _active_signal_summary(session, now=generated_at)
    drift = await _drift_runtime_snapshot(session)
    calibration_samples = await _calibration_samples(
        session,
        now=generated_at,
        lookback_days=calibration_lookback_days,
    )
    scheduler = _scheduler_runtime_snapshot(get_scheduler().health_summary())
    latest_at = _latest_datetime(latest_signal_at, drift.latest_at, _parse_datetime(scheduler.last_activity))

    return RuntimeHeartbeatSnapshot(
        generated_at=generated_at,
        latest_at=latest_at,
        active_signals=active_signals,
        drift=drift,
        calibration=RuntimeCalibrationSnapshot(
            samples=calibration_samples,
            lookback_days=calibration_lookback_days,
        ),
        scheduler=scheduler,
        status=_heartbeat_status(scheduler),
    )


async def _active_signal_summary(
    session: AsyncSession,
    *,
    now: datetime,
) -> tuple[int, datetime | None]:
    result = await session.execute(_active_signal_summary_statement(now=now))
    count, latest_at = result.one()
    return int(count or 0), latest_at


def _active_signal_summary_statement(*, now: datetime):
    cutoff = now - timedelta(hours=ACTIVE_SIGNAL_FRESHNESS_HOURS)
    return select(func.count(SignalTrack.id), func.max(SignalTrack.created_at)).where(
        SignalTrack.created_at >= cutoff
    )


async def _drift_runtime_snapshot(session: AsyncSession) -> RuntimeDriftSnapshot:
    rows = list((await session.scalars(_recent_drift_statement(limit=DEFAULT_DRIFT_LIMIT))).all())
    return _drift_snapshot_to_runtime(build_drift_snapshot(rows))


def _recent_drift_statement(*, limit: int):
    return (
        select(DriftMetric)
        .order_by(DriftMetric.computed_at.desc(), DriftMetric.id.desc())
        .limit(limit)
    )


def _drift_snapshot_to_runtime(snapshot: DriftSnapshotRead) -> RuntimeDriftSnapshot:
    return RuntimeDriftSnapshot(
        status=snapshot.status,
        latest_at=snapshot.latest_at,
        notification=RuntimeDriftNotification(
            level=snapshot.notification.level,
            title=snapshot.notification.title,
            should_notify=snapshot.notification.should_notify,
        ),
    )


async def _calibration_samples(
    session: AsyncSession,
    *,
    now: datetime,
    lookback_days: int,
) -> int:
    value = await session.scalar(
        _calibration_samples_statement(now=now, lookback_days=lookback_days)
    )
    return int(value or 0)


def _calibration_samples_statement(*, now: datetime, lookback_days: int):
    since = now - timedelta(days=lookback_days)
    return select(func.count(SignalTrack.id)).where(
        SignalTrack.created_at >= since,
        SignalTrack.created_at <= now,
        SignalTrack.outcome.in_(RESOLVED_OUTCOMES),
    )


def _scheduler_runtime_snapshot(health: dict) -> RuntimeSchedulerSnapshot:
    return RuntimeSchedulerSnapshot(
        degraded_jobs=list(health.get("degraded_jobs") or []),
        warning_jobs=list(health.get("warning_jobs") or []),
        unconfigured_jobs=list(health.get("unconfigured_jobs") or []),
        last_activity=health.get("last_activity"),
        handler_coverage={
            str(key): int(value)
            for key, value in dict(health.get("handler_coverage") or {}).items()
            if isinstance(value, int)
        },
    )


def _heartbeat_status(scheduler: RuntimeSchedulerSnapshot) -> Literal["running", "scheduler_degraded"]:
    if scheduler.degraded_jobs or scheduler.warning_jobs or scheduler.unconfigured_jobs:
        return "scheduler_degraded"
    return "running"


def _latest_datetime(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return max(_aware_datetime(value) for value in present)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _runtime_heartbeat_cache_key(*, calibration_lookback_days: int) -> RuntimeHeartbeatCacheKey:
    return (calibration_lookback_days,)


def _runtime_heartbeat_cache_get(
    key: RuntimeHeartbeatCacheKey,
    *,
    now: datetime | None = None,
) -> RuntimeHeartbeatSnapshot | None:
    current = now or datetime.now(timezone.utc)
    cached = _RUNTIME_HEARTBEAT_CACHE.get(key)
    if cached is None:
        return None
    cached_at, snapshot = cached
    if (current - cached_at).total_seconds() > RUNTIME_HEARTBEAT_CACHE_TTL_SECONDS:
        _RUNTIME_HEARTBEAT_CACHE.pop(key, None)
        return None
    return snapshot.model_copy(deep=True)


def _runtime_heartbeat_cache_set(
    key: RuntimeHeartbeatCacheKey,
    snapshot: RuntimeHeartbeatSnapshot,
    *,
    now: datetime | None = None,
) -> None:
    if len(_RUNTIME_HEARTBEAT_CACHE) >= RUNTIME_HEARTBEAT_CACHE_MAX_ENTRIES and key not in _RUNTIME_HEARTBEAT_CACHE:
        oldest_key = min(_RUNTIME_HEARTBEAT_CACHE, key=lambda item: _RUNTIME_HEARTBEAT_CACHE[item][0])
        _RUNTIME_HEARTBEAT_CACHE.pop(oldest_key, None)
    _RUNTIME_HEARTBEAT_CACHE[key] = (
        now or datetime.now(timezone.utc),
        snapshot.model_copy(deep=True),
    )


def _clear_runtime_heartbeat_cache() -> None:
    _RUNTIME_HEARTBEAT_CACHE.clear()
