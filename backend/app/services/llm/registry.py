from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.core.config import Settings, get_settings
from app.models.llm_config import LLMConfig as LLMConfigModel
from app.services.llm.anthropic import AnthropicProvider
from app.services.llm.deepseek import DeepSeekProvider
from app.services.llm.openai import OpenAIProvider
from app.services.llm.types import (
    DEFAULT_MODELS,
    LLMCompletionOptions,
    LLMCompletionResult,
    LLMConfigurationError,
    LLMProvider,
    LLMProviderConfig,
    LLMProviderName,
)
from app.services.llm.budget_guard import add_budget_spend, check_llm_budget
from app.services.llm.cache import get_cached_completion, llm_cache_key, messages_to_prompt_parts, store_cached_completion
from app.services.llm.cost_tracker import estimate_cost_usd, record_llm_usage

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
        await rollback_if_possible(session)
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


async def complete_with_llm_controls(
    *,
    module: str,
    options: LLMCompletionOptions,
    session: AsyncSession | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> LLMCompletionResult:
    config = await get_active_llm_config(session=session)
    if config is None:
        config = get_env_llm_config(settings or get_settings())
    if config is None:
        raise LLMConfigurationError(
            "No LLM provider configured. Enable a DB config or set an LLM API key env var."
        )

    budget = await check_llm_budget(session, module=module)
    if not budget.allowed:
        await record_llm_usage(
            session,
            module=module,
            provider=config.provider,
            model=config.model,
            status="budget_blocked",
            error=budget.reason,
        )
        raise LLMConfigurationError(f"LLM budget blocked for {module}: {budget.reason}")

    system, user = messages_to_prompt_parts(options.messages)
    cache_key = llm_cache_key(
        provider=config.provider,
        model=config.model,
        system=system,
        user=user,
    )
    cached = await get_cached_completion(session, cache_key=cache_key)
    if cached is not None:
        await record_llm_usage(
            session,
            module=module,
            provider=config.provider,
            model=config.model,
            cache_hit=True,
            status="cache_hit",
        )
        return cached

    provider = create_provider(config, client=client)
    try:
        result = await provider.complete(options)
    except Exception as exc:
        await record_llm_usage(
            session,
            module=module,
            provider=config.provider,
            model=config.model,
            status="error",
            error=str(exc),
        )
        raise

    input_tokens = result.usage.input_tokens if result.usage and result.usage.input_tokens else 0
    output_tokens = result.usage.output_tokens if result.usage and result.usage.output_tokens else 0
    estimated_cost = estimate_cost_usd(result.model, input_tokens, output_tokens)
    await store_cached_completion(
        session,
        cache_key=cache_key,
        module=module,
        provider=config.provider,
        model=result.model,
        system=system,
        user=user,
        result=result,
    )
    await record_llm_usage(
        session,
        module=module,
        provider=config.provider,
        model=result.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
        cache_hit=False,
    )
    await add_budget_spend(session, module=module, amount_usd=estimated_cost)
    return result
