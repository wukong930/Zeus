import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_cache import LLMCache
from app.services.llm.types import LLMCompletionResult, LLMUsage


def llm_cache_key(*, provider: str, model: str, system: str, user: str) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "system": system,
        "user": user,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
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
        return None
    if row is None:
        return None
    row.hit_count = int(row.hit_count or 0) + 1
    row.updated_at = effective_at
    await session.flush()
    usage = row.response.get("usage") or {}
    return LLMCompletionResult(
        content=str(row.response.get("content") or ""),
        model=str(row.response.get("model") or row.model),
        usage=LLMUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        ),
        raw=row.response.get("raw"),
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
    row = LLMCache(
        cache_key=cache_key,
        module=module,
        provider=provider,
        model=model,
        system_hash=prompt_hash(system),
        user_hash=prompt_hash(user),
        response={
            "content": result.content,
            "model": result.model,
            "usage": {
                "input_tokens": result.usage.input_tokens if result.usage else None,
                "output_tokens": result.usage.output_tokens if result.usage else None,
            },
            "raw": result.raw,
        },
        hit_count=0,
        expires_at=effective_at + ttl,
    )
    session.add(row)
    await session.flush()
    return row


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
