from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.llm_config import LLMConfig as LLMConfigModel
from app.services.llm.anthropic import AnthropicProvider
from app.services.llm.deepseek import DeepSeekProvider
from app.services.llm.openai import OpenAIProvider
from app.services.llm.types import (
    DEFAULT_MODELS,
    LLMConfigurationError,
    LLMProvider,
    LLMProviderConfig,
    LLMProviderName,
)

ProviderFactory = Callable[[LLMProviderConfig, httpx.AsyncClient | None], LLMProvider]


def _create_openai(config: LLMProviderConfig, client: httpx.AsyncClient | None) -> LLMProvider:
    return OpenAIProvider(config, client=client)


def _create_anthropic(config: LLMProviderConfig, client: httpx.AsyncClient | None) -> LLMProvider:
    return AnthropicProvider(config, client=client)


def _create_deepseek(config: LLMProviderConfig, client: httpx.AsyncClient | None) -> LLMProvider:
    return DeepSeekProvider(config, client=client)


PROVIDER_FACTORIES: dict[LLMProviderName, ProviderFactory] = {
    "openai": _create_openai,
    "anthropic": _create_anthropic,
    "deepseek": _create_deepseek,
}


def create_provider(
    config: LLMProviderConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> LLMProvider:
    factory = PROVIDER_FACTORIES.get(config.provider)
    if factory is None:
        raise LLMConfigurationError(f"Unknown LLM provider: {config.provider}")
    if not config.enabled:
        raise LLMConfigurationError(f"LLM provider is disabled: {config.provider}")
    if not _clean_secret(config.api_key):
        raise LLMConfigurationError(f"Missing API key for LLM provider: {config.provider}")
    return factory(config, client)


async def get_active_llm_provider(
    *,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> LLMProvider:
    config = await get_active_llm_config(session=session)
    if config is None:
        config = get_env_llm_config(settings or get_settings())
    if config is None:
        raise LLMConfigurationError(
            "No LLM provider configured. Enable a DB config or set an LLM API key env var."
        )
    return create_provider(config, client=client)


async def get_active_llm_config(
    *,
    session: AsyncSession | None = None,
) -> LLMProviderConfig | None:
    if session is None:
        return None

    try:
        row = (
            await session.scalars(
                select(LLMConfigModel)
                .where(LLMConfigModel.enabled.is_(True))
                .order_by(LLMConfigModel.updated_at.desc())
                .limit(1)
            )
        ).first()
    except Exception:
        return None

    if row is None:
        return None

    provider = str(row.provider).lower()
    if provider not in PROVIDER_FACTORIES:
        return None

    settings = get_settings()
    return LLMProviderConfig(
        provider=provider,  # type: ignore[arg-type]
        api_key=row.api_key,
        model=row.model,
        enabled=row.enabled,
        base_url=row.base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def get_env_llm_config(settings: Settings) -> LLMProviderConfig | None:
    if api_key := _clean_secret(settings.openai_api_key):
        return LLMProviderConfig(
            provider="openai",
            api_key=api_key,
            model=settings.llm_model or DEFAULT_MODELS["openai"][0],
            base_url=settings.openai_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if api_key := _clean_secret(settings.anthropic_api_key):
        return LLMProviderConfig(
            provider="anthropic",
            api_key=api_key,
            model=settings.llm_model or DEFAULT_MODELS["anthropic"][0],
            base_url=settings.anthropic_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if api_key := _clean_secret(settings.deepseek_api_key):
        return LLMProviderConfig(
            provider="deepseek",
            api_key=api_key,
            model=settings.llm_model or DEFAULT_MODELS["deepseek"][0],
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    return None


def _clean_secret(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
