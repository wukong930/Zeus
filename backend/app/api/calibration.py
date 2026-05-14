from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.calibration.dashboard import summarize_calibration_dashboard

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


@router.get("/dashboard")
async def get_calibration_dashboard(
    lookback_days: int = Query(default=180, ge=7, le=730),
    min_samples: int = Query(default=1, ge=1, le=500),
    limit: int = Query(default=100, ge=1, le=300),
    session: AsyncSession = Depends(get_db),
) -> dict:
    dashboard = await summarize_calibration_dashboard(
        session,
        lookback_days=lookback_days,
        min_samples=min_samples,
        limit=limit,
    )
    return dashboard.to_dict()
