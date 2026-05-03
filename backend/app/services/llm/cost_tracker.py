from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_cache import LLMUsageLog


@dataclass(frozen=True)
class LLMUsageSummary:
    module: str
    period_start: date
    period_end: date
    calls: int
    cache_hits: int
    estimated_cost_usd: float
    input_tokens: int
    output_tokens: int


async def record_llm_usage(
    session: AsyncSession | None,
    *,
    module: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float | None = None,
    cache_hit: bool = False,
    status: str = "ok",
    error: str | None = None,
) -> LLMUsageLog | None:
    if session is None:
        return None
    row = LLMUsageLog(
        module=module,
        provider=provider,
        model=model,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        estimated_cost_usd=(
            estimate_cost_usd(model, input_tokens, output_tokens)
            if estimated_cost_usd is None
            else estimated_cost_usd
        ),
        cache_hit=cache_hit,
        status=status,
        error=error,
    )
    session.add(row)
    await session.flush()
    return row


async def monthly_usage_summary(
    session: AsyncSession,
    *,
    module: str,
    period_start: date,
    period_end: date,
) -> LLMUsageSummary:
    result = (
        await session.execute(
            select(
                func.count(LLMUsageLog.id),
                func.count(LLMUsageLog.id).filter(LLMUsageLog.cache_hit.is_(True)),
                func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0),
                func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
                func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
            ).where(
                LLMUsageLog.module == module,
                LLMUsageLog.created_at >= datetime.combine(
                    period_start,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
                LLMUsageLog.created_at
                < datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
    ).one()
    return LLMUsageSummary(
        module=module,
        period_start=period_start,
        period_end=period_end,
        calls=int(result[0] or 0),
        cache_hits=int(result[1] or 0),
        estimated_cost_usd=float(result[2] or 0),
        input_tokens=int(result[3] or 0),
        output_tokens=int(result[4] or 0),
    )


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if input_tokens <= 0 and output_tokens <= 0:
        return 0.0
    lowered = model.lower()
    if "mini" in lowered or "haiku" in lowered:
        input_rate = 0.0002
        output_rate = 0.0008
    elif "reasoner" in lowered or "opus" in lowered:
        input_rate = 0.003
        output_rate = 0.015
    else:
        input_rate = 0.001
        output_rate = 0.004
    return round((input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate, 6)
