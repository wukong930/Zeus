from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import LLMUsageSummaryRead
from app.services.llm.budget_guard import month_bounds
from app.services.llm.cost_tracker import (
    MAX_LLM_MODULE_LENGTH,
    monthly_usage_summary,
    normalize_llm_module,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/usage", response_model=LLMUsageSummaryRead)
async def get_llm_usage(
    module: str = Query(
        default="alert_agent",
        min_length=1,
        max_length=MAX_LLM_MODULE_LENGTH,
    ),
    month: date | None = None,
    session: AsyncSession = Depends(get_db),
) -> LLMUsageSummaryRead:
    normalized_module = normalize_llm_module(module)
    period_start, period_end = month_bounds(month or date.today())
    summary = await monthly_usage_summary(
        session,
        module=normalized_module,
        period_start=period_start,
        period_end=period_end,
    )
    return LLMUsageSummaryRead(**summary.__dict__)
