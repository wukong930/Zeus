from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.contract_metadata import ContractMetadata
from app.schemas.common import ContractCreate, ContractRead, MAX_INGEST_SYMBOL_LENGTH

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.get("", response_model=list[ContractRead])
async def list_contracts(
    symbol: str | None = Query(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH),
    is_main: bool | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[ContractMetadata]:
    statement = select(ContractMetadata).order_by(ContractMetadata.symbol, ContractMetadata.contract_month)
    if symbol is not None:
        statement = statement.where(ContractMetadata.symbol == symbol)
    if is_main is not None:
        statement = statement.where(ContractMetadata.is_main == is_main)
    return list((await session.scalars(statement.limit(limit))).all())


@router.post("", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    session: AsyncSession = Depends(get_db),
) -> ContractMetadata:
    data = payload.model_dump(exclude_none=True)
    row = ContractMetadata(**data)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ContractMetadata:
    row = await session.get(ContractMetadata, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return row
