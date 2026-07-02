"""Deployment-hardening edge cases: rate limiting + the CORS wildcard guardrail."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import PUBLIC_PATHS
from app.core.config import get_settings
from app.core.rate_limit import RateLimitMiddleware
from app.main import create_app


def _rate_limited_app(limit: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit, exempt_paths=PUBLIC_PATHS)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def test_rate_limit_blocks_after_limit() -> None:
    client = TestClient(_rate_limited_app(2))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_rate_limit_exempts_health_probes() -> None:
    # health is exempt so load balancers are never throttled, even past the limit
    client = TestClient(_rate_limited_app(1))
    for _ in range(5):
        assert client.get("/api/health").status_code == 200


def test_rate_limit_disabled_when_zero() -> None:
    client = TestClient(_rate_limited_app(0))
    for _ in range(5):
        assert client.get("/ping").status_code == 200


def test_cors_wildcard_disables_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.delenv("API_KEYS", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        response = client.get("/api/health", headers={"Origin": "http://anything.example"})
        assert response.status_code == 200
        header_names = {name.lower() for name in response.headers}
        # '*' and credentials cannot coexist -> the credentials header is suppressed
        assert "access-control-allow-credentials" not in header_names
        assert response.headers.get("access-control-allow-origin") == "*"
    finally:
        get_settings.cache_clear()


def test_cors_explicit_origin_allows_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://app.example")
    monkeypatch.delenv("API_KEYS", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        response = client.get("/api/health", headers={"Origin": "http://app.example"})
        assert response.headers.get("access-control-allow-credentials") == "true"
        assert response.headers.get("access-control-allow-origin") == "http://app.example"
    finally:
        get_settings.cache_clear()
