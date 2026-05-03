from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.contracts import router as contracts_router
from app.api.health import router as health_router
from app.api.industry_data import router as industry_data_router
from app.api.market_data import router as market_data_router
from app.api.positions import router as positions_router
from app.api.recommendations import router as recommendations_router
from app.api.scheduler import router as scheduler_router
from app.api.strategies import router as strategies_router
from app.core.config import get_settings
from app.core.redis import close_redis
from app.scheduler.manager import get_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = get_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Python control plane for Zeus.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(market_data_router)
    app.include_router(industry_data_router)
    app.include_router(contracts_router)
    app.include_router(alerts_router)
    app.include_router(positions_router)
    app.include_router(recommendations_router)
    app.include_router(strategies_router)
    app.include_router(scheduler_router)
    return app


app = create_app()
