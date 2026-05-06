from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert_agent import AlertAgentConfig
from app.services.llm.registry import get_active_llm_config, get_env_llm_config
from app.services.llm.types import DEFAULT_MODELS, LLMProviderConfig, LLMProviderName
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
PROVIDER_LABELS: dict[LLMProviderName, str] = {
    "xai": "xAI Grok",
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
}
PROVIDER_ORDER: tuple[LLMProviderName, ...] = ("xai", "anthropic", "openai", "deepseek")


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


class LLMProviderSettingsRead(BaseModel):
    provider: str
    name: str
    model: str | None
    configured: bool
    active: bool
    source: str
    status: str
    reason: str | None = None


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


@router.get("/llm-providers", response_model=list[LLMProviderSettingsRead])
async def get_llm_provider_settings(
    session: AsyncSession = Depends(get_db),
) -> list[LLMProviderSettingsRead]:
    return await load_llm_provider_settings(session)


async def load_llm_provider_settings(session: AsyncSession) -> list[LLMProviderSettingsRead]:
    from app.core.config import get_settings

    settings = get_settings()
    db_active = await get_active_llm_config(session=session)
    env_active = get_env_llm_config(settings)
    active = db_active or env_active
    active_source = "database" if db_active is not None else "environment" if env_active else None

    return [
        _llm_provider_read(
            provider,
            active=active,
            active_source=active_source,
            settings=settings,
        )
        for provider in PROVIDER_ORDER
    ]


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


def _llm_provider_read(
    provider: LLMProviderName,
    *,
    active: LLMProviderConfig | None,
    active_source: str | None,
    settings: Any,
) -> LLMProviderSettingsRead:
    env_config = _env_provider_config(provider, settings)
    is_active = active is not None and active.provider == provider
    configured = is_active or env_config is not None
    source = active_source if is_active and active_source else "environment" if env_config else "not_configured"
    model = active.model if is_active and active is not None else env_config.model if env_config else None
    status = "active" if is_active else "configured" if configured else "unconfigured"
    reason = None if configured else _missing_key_reason(provider)
    return LLMProviderSettingsRead(
        provider=provider,
        name=PROVIDER_LABELS[provider],
        model=model,
        configured=configured,
        active=is_active,
        source=source,
        status=status,
        reason=reason,
    )


def _env_provider_config(
    provider: LLMProviderName,
    settings: Any,
) -> LLMProviderConfig | None:
    api_key = {
        "openai": settings.openai_api_key,
        "xai": settings.xai_api_key,
        "anthropic": settings.anthropic_api_key,
        "deepseek": settings.deepseek_api_key,
    }[provider]
    if not _has_secret(api_key):
        return None
    return LLMProviderConfig(
        provider=provider,
        api_key=str(api_key),
        model=settings.llm_model or DEFAULT_MODELS[provider][0],
        base_url={
            "openai": settings.openai_base_url,
            "xai": settings.xai_base_url,
            "anthropic": settings.anthropic_base_url,
            "deepseek": settings.deepseek_base_url,
        }[provider],
        timeout_seconds=settings.llm_timeout_seconds,
    )


def _has_secret(value: str | None) -> bool:
    return bool(value and value.strip())


def _missing_key_reason(provider: LLMProviderName) -> str:
    return {
        "openai": "OPENAI_API_KEY is not configured",
        "xai": "XAI_API_KEY is not configured",
        "anthropic": "ANTHROPIC_API_KEY is not configured",
        "deepseek": "DEEPSEEK_API_KEY is not configured",
    }[provider]
