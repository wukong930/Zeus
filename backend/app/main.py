import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import PUBLIC_PATHS, verify_api_key
from app.core.rate_limit import RateLimitMiddleware

from app.api.alerts import router as alerts_router
from app.api.arbitration import router as arbitration_router
from app.api.calibration import router as calibration_router
from app.api.attribution import router as attribution_router
from app.api.causal_web import router as causal_web_router
from app.api.contracts import router as contracts_router
from app.api.cost_models import router as cost_models_router
from app.api.data_sources import router as data_sources_router
from app.api.drift import router as drift_router
from app.api.event_intelligence import router as event_intelligence_router
from app.api.feedback import router as feedback_router
from app.api.forecast import router as forecast_router
from app.api.governance import router as governance_router
from app.api.health import router as health_router
from app.api.industry_data import router as industry_data_router
from app.api.learning import router as learning_router
from app.api.llm_usage import router as llm_usage_router
from app.api.market_data import router as market_data_router
from app.api.news_events import router as news_events_router
from app.api.notebook import router as notebook_router
from app.api.positions import router as positions_router
from app.api.recommendations import router as recommendations_router
from app.api.risk import router as risk_router
from app.api.runtime import router as runtime_router
from app.api.scenarios import router as scenarios_router
from app.api.scheduler import router as scheduler_router
from app.api.settings import router as settings_router
from app.api.shadow import router as shadow_router
from app.api.strategies import router as strategies_router
from app.api.world_map import router as world_map_router
from app.core.config import get_settings
from app.core.redis import close_redis
from app.scheduler.manager import get_scheduler
from app.services.pipeline.runtime import get_event_pipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = get_scheduler()
    event_pipeline = get_event_pipeline()
    await event_pipeline.start()
    scheduler.start()
    yield
    scheduler.shutdown()
    await event_pipeline.stop()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    auth_enabled = settings.auth_enabled

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Python control plane for Zeus.",
        lifespan=lifespan,
        # global gate — every route runs through verify_api_key (health is exempt)
        dependencies=[Depends(verify_api_key)],
        # close the schema/docs when auth is on (they'd otherwise expose the API surface)
        docs_url=None if auth_enabled else "/docs",
        redoc_url=None if auth_enabled else "/redoc",
        openapi_url=None if auth_enabled else "/openapi.json",
    )

    # A wildcard origin cannot coexist with credentials (the browser forbids it and
    # it's a real footgun); if '*' is configured, disable credentials rather than
    # silently run an insecure/invalid CORS policy.
    cors_wildcard = "*" in settings.cors_origins
    if cors_wildcard:
        logger.warning(
            "CORS allow_origins contains '*'; disabling allow_credentials (they cannot coexist)."
        )

    # Rate limit is added first so CORS (added last) stays OUTERMOST: a 429 short
    # circuit still passes back through CORS and carries headers the browser can read.
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
        exempt_paths=PUBLIC_PATHS,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=not cors_wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(arbitration_router)
    app.include_router(calibration_router)
    app.include_router(attribution_router)
    app.include_router(causal_web_router)
    app.include_router(market_data_router)
    app.include_router(news_events_router)
    app.include_router(notebook_router)
    app.include_router(industry_data_router)
    app.include_router(feedback_router)
    app.include_router(forecast_router)
    app.include_router(governance_router)
    app.include_router(learning_router)
    app.include_router(llm_usage_router)
    app.include_router(contracts_router)
    app.include_router(cost_models_router)
    app.include_router(data_sources_router)
    app.include_router(drift_router)
    app.include_router(event_intelligence_router)
    app.include_router(alerts_router)
    app.include_router(positions_router)
    app.include_router(recommendations_router)
    app.include_router(risk_router)
    app.include_router(runtime_router)
    app.include_router(scenarios_router)
    app.include_router(shadow_router)
    app.include_router(strategies_router)
    app.include_router(scheduler_router)
    app.include_router(settings_router)
    app.include_router(world_map_router)
    return app


app = create_app()
