from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.industry_data import IndustryData
from app.schemas.common import IndustryDataCreate, IndustryDataRead
from app.services.etl.writers import append_industry_data
from app.services.market_data.pit import get_industry_data_pit

router = APIRouter(prefix="/api/industry-data", tags=["industry-data"])


@router.get("", response_model=list[IndustryDataRead])
async def list_industry_data(
    symbol: str,
    data_type: str | None = None,
    as_of: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_db),
) -> list[IndustryData]:
    return await get_industry_data_pit(
        session,
        symbol=symbol,
        data_type=data_type,
        as_of=as_of,
        start=start,
        end=end,
        limit=limit,
    )


@router.post("", response_model=IndustryDataRead, status_code=status.HTTP_201_CREATED)
async def create_industry_data(
    payload: IndustryDataCreate,
    session: AsyncSession = Depends(get_db),
) -> IndustryData:
    row = (await append_industry_data(session, [payload]))[0]
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{industry_data_id}", response_model=IndustryDataRead)
async def get_industry_data(
    industry_data_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> IndustryData:
    row = await session.get(IndustryData, industry_data_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Industry data row not found")
    return row
