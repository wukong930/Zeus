from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import verify_api_key
from app.core.config import get_settings
from app.main import create_app


def _request(path: str) -> SimpleNamespace:
    return SimpleNamespace(url=SimpleNamespace(path=path))


async def test_auth_disabled_when_no_keys(monkeypatch):
    monkeypatch.delenv("API_KEYS", raising=False)
    get_settings.cache_clear()
    try:
        # no keys configured -> any request passes (local dev)
        await verify_api_key(_request("/api/market-data"), api_key=None)
    finally:
        get_settings.cache_clear()


async def test_auth_enforced_with_keys(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123, other-key")
    get_settings.cache_clear()
    try:
        # protected route, missing key -> 401
        with pytest.raises(HTTPException) as missing:
            await verify_api_key(_request("/api/governance/reviews"), api_key=None)
        assert missing.value.status_code == 401

        # wrong key -> 401
        with pytest.raises(HTTPException):
            await verify_api_key(_request("/api/governance/reviews"), api_key="nope")

        # correct key -> allowed
        await verify_api_key(_request("/api/governance/reviews"), api_key="secret123")
        await verify_api_key(_request("/api/governance/reviews"), api_key="other-key")

        # health probes stay public even without a key
        await verify_api_key(_request("/api/health"), api_key=None)
        await verify_api_key(_request("/api/health/ready"), api_key=None)
    finally:
        get_settings.cache_clear()


def test_app_blocks_protected_route_and_keeps_health_public(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        # health is reachable without a key
        assert client.get("/api/health").status_code == 200
        # a protected route is blocked before it ever reaches the DB
        assert client.get("/api/governance/reviews").status_code == 401
        # schema is closed when auth is on
        assert client.get("/openapi.json").status_code == 404
    finally:
        get_settings.cache_clear()


def test_app_open_for_local_dev_without_keys(monkeypatch):
    monkeypatch.delenv("API_KEYS", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/api/health").status_code == 200
        # docs are available in dev
        assert client.get("/openapi.json").status_code == 200
    finally:
        get_settings.cache_clear()
