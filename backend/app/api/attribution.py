from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.learning.attribution_report import generate_attribution_report
from app.services.llm.budget_guard import month_bounds

router = APIRouter(prefix="/api/attribution", tags=["attribution"])


@router.get("/report")
async def get_attribution_report(
    month: date | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict:
    period_start, period_end = month_bounds(month or date.today())
    report = await generate_attribution_report(
        session,
        period_start=period_start,
        period_end=period_end,
    )
    return report.to_dict()
