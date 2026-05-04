from fastapi import APIRouter

from app.services.data_sources.registry import data_source_statuses

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


@router.get("")
async def list_data_sources() -> list[dict]:
    return [status.to_dict() for status in data_source_statuses()]
