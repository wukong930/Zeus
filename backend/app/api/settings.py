from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert_agent import AlertAgentConfig
from app.services.alert_agent.dedup import (
    DEFAULT_COMBINATION_WINDOW_HOURS,
    DEFAULT_DAILY_ALERT_LIMIT,
    DEFAULT_REPEAT_WINDOW_HOURS,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

NOTIFICATION_SETTINGS_KEY = "notification_channels"
DEFAULT_NOTIFICATION_SETTINGS = {
    "realtime_sse": True,
    "feishu_webhook": False,
    "email": False,
    "custom_webhook": False,
}


class AlertDedupSettingsRead(BaseModel):
    repeat_window_hours: int
    combination_window_hours: int
    daily_alert_limit: int
    allow_severity_upgrade_resend: bool
    source: str


class NotificationSettingsRead(BaseModel):
    realtime_sse: bool
    feishu_webhook: bool
    email: bool
    custom_webhook: bool
    source: str


class NotificationSettingsUpdate(BaseModel):
    realtime_sse: bool | None = None
    feishu_webhook: bool | None = None
    email: bool | None = None
    custom_webhook: bool | None = None


@router.get("/alert-dedup", response_model=AlertDedupSettingsRead)
async def get_alert_dedup_settings() -> AlertDedupSettingsRead:
    return AlertDedupSettingsRead(
        repeat_window_hours=DEFAULT_REPEAT_WINDOW_HOURS,
        combination_window_hours=DEFAULT_COMBINATION_WINDOW_HOURS,
        daily_alert_limit=DEFAULT_DAILY_ALERT_LIMIT,
        allow_severity_upgrade_resend=True,
        source="backend_defaults",
    )


@router.get("/notifications", response_model=NotificationSettingsRead)
async def get_notification_settings(
    session: AsyncSession = Depends(get_db),
) -> NotificationSettingsRead:
    return await load_notification_settings(session)


@router.put("/notifications", response_model=NotificationSettingsRead)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    session: AsyncSession = Depends(get_db),
) -> NotificationSettingsRead:
    return await save_notification_settings(session, payload)


async def load_notification_settings(session: AsyncSession) -> NotificationSettingsRead:
    row = await _notification_config_row(session)
    if row is None:
        return _notification_read(DEFAULT_NOTIFICATION_SETTINGS, source="backend_defaults")
    return _notification_read(row.value or {}, source="database")


async def save_notification_settings(
    session: AsyncSession,
    payload: NotificationSettingsUpdate,
) -> NotificationSettingsRead:
    row = await _notification_config_row(session)
    current = dict(DEFAULT_NOTIFICATION_SETTINGS)
    if row is not None:
        current.update(_notification_values(row.value or {}))

    updates = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }
    current.update(updates)
    persisted = _notification_values(current)

    if row is None:
        row = AlertAgentConfig(key=NOTIFICATION_SETTINGS_KEY, value=persisted)
        session.add(row)
    else:
        row.value = persisted

    await session.commit()
    return _notification_read(persisted, source="database")


async def _notification_config_row(session: AsyncSession) -> AlertAgentConfig | None:
    return (
        await session.scalars(
            select(AlertAgentConfig)
            .where(AlertAgentConfig.key == NOTIFICATION_SETTINGS_KEY)
            .limit(1)
        )
    ).first()


def _notification_read(values: dict[str, Any], *, source: str) -> NotificationSettingsRead:
    merged = _notification_values(values)
    return NotificationSettingsRead(source=source, **merged)


def _notification_values(values: dict[str, Any]) -> dict[str, bool]:
    return {
        key: _bool_value(values.get(key), default)
        for key, default in DEFAULT_NOTIFICATION_SETTINGS.items()
    }


def _bool_value(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default
