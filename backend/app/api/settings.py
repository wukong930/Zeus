from fastapi import APIRouter
from pydantic import BaseModel

from app.services.alert_agent.dedup import (
    DEFAULT_COMBINATION_WINDOW_HOURS,
    DEFAULT_DAILY_ALERT_LIMIT,
    DEFAULT_REPEAT_WINDOW_HOURS,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AlertDedupSettingsRead(BaseModel):
    repeat_window_hours: int
    combination_window_hours: int
    daily_alert_limit: int
    allow_severity_upgrade_resend: bool
    source: str


@router.get("/alert-dedup", response_model=AlertDedupSettingsRead)
async def get_alert_dedup_settings() -> AlertDedupSettingsRead:
    return AlertDedupSettingsRead(
        repeat_window_hours=DEFAULT_REPEAT_WINDOW_HOURS,
        combination_window_hours=DEFAULT_COMBINATION_WINDOW_HOURS,
        daily_alert_limit=DEFAULT_DAILY_ALERT_LIMIT,
        allow_severity_upgrade_resend=True,
        source="backend_defaults",
    )
