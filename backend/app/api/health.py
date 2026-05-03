from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.core.database import ping_database
from app.core.redis import ping_redis

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health/ready")
async def readiness_check(response: Response) -> dict[str, object]:
    checks = {
        "database": await ping_database(),
        "redis": await ping_redis(),
    }
    ready = all(checks.values())

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if ready else "degraded",
        "checks": checks,
    }
