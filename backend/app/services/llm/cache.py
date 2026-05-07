import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.llm_cache import LLMCache
from app.services.llm.types import LLMCompletionResult, LLMUsage


def llm_cache_key(
    *,
    provider: str,
    model: str,
    system: str,
    user: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
    json_schema: dict[str, Any] | None = None,
) -> str:
    payload = {
        "version": 2,
        "provider": provider,
        "model": model,
        "system": system,
        "user": user,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "json_mode": json_mode,
        "json_schema": json_schema,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def get_cached_completion(
    session: AsyncSession | None,
    *,
    cache_key: str,
    as_of: datetime | None = None,
) -> LLMCompletionResult | None:
    if session is None:
        return None
    effective_at = as_of or datetime.now(timezone.utc)
    try:
        row = (
            await session.scalars(
                select(LLMCache)
                .where(
                    LLMCache.cache_key == cache_key,
                    LLMCache.expires_at > effective_at,
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return None
    if row is None:
        return None
    response = dict(row.response or {})
    model = str(response.get("model") or row.model)
    try:
        row.hit_count = int(row.hit_count or 0) + 1
        row.updated_at = effective_at
        await session.flush()
    except Exception:
        await rollback_if_possible(session)
    usage = response.get("usage") or {}
    return LLMCompletionResult(
        content=str(response.get("content") or ""),
        model=model,
        usage=LLMUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        ),
        raw=response.get("raw"),
    )


async def store_cached_completion(
    session: AsyncSession | None,
    *,
    cache_key: str,
    module: str,
    provider: str,
    model: str,
    system: str,
    user: str,
    result: LLMCompletionResult,
    ttl: timedelta = timedelta(hours=24),
    as_of: datetime | None = None,
) -> LLMCache | None:
    if session is None:
        return None
    effective_at = as_of or datetime.now(timezone.utc)
    try:
        row = (
            await session.scalars(select(LLMCache).where(LLMCache.cache_key == cache_key).limit(1))
        ).first()
        expires_at = effective_at + ttl
        if row is None:
            row = LLMCache(cache_key=cache_key)
            session.add(row)
        _apply_cached_completion(
            row,
            module=module,
            provider=provider,
            model=model,
            system=system,
            user=user,
            result=result,
            expires_at=expires_at,
            updated_at=effective_at,
        )
        await session.flush()
        return row
    except Exception:
        await rollback_if_possible(session)
        return None


def messages_to_prompt_parts(messages: list[dict[str, Any]] | Any) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for message in messages:
        role = getattr(message, "role", None) or message.get("role")
        content = getattr(message, "content", None) or message.get("content") or ""
        if role == "system":
            system_parts.append(str(content))
        elif role == "user":
            user_parts.append(str(content))
    return "\n".join(system_parts), "\n".join(user_parts)


def _apply_cached_completion(
    row: LLMCache,
    *,
    module: str,
    provider: str,
    model: str,
    system: str,
    user: str,
    result: LLMCompletionResult,
    expires_at: datetime,
    updated_at: datetime,
) -> None:
    row.module = module
    row.provider = provider
    row.model = model
    row.system_hash = prompt_hash(system)
    row.user_hash = prompt_hash(user)
    row.response = {
        "content": result.content,
        "model": result.model,
        "usage": {
            "input_tokens": result.usage.input_tokens if result.usage else None,
            "output_tokens": result.usage.output_tokens if result.usage else None,
        },
        "raw": result.raw,
    }
    row.hit_count = 0
    row.expires_at = expires_at
    row.updated_at = updated_at
