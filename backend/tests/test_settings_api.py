from fastapi.testclient import TestClient

from app.api.settings import NotificationSettingsRead
from app.core.config import Settings
from app.core.database import get_db
from app.main import create_app
from app.services.alert_agent.dedup import (
    DEFAULT_COMBINATION_WINDOW_HOURS,
    DEFAULT_DAILY_ALERT_LIMIT,
    DEFAULT_REPEAT_WINDOW_HOURS,
)
from app.services.llm.types import LLMProviderConfig


def test_alert_dedup_settings_exposes_backend_defaults() -> None:
    client = TestClient(create_app())

    response = client.get("/api/settings/alert-dedup")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "repeat_window_hours": DEFAULT_REPEAT_WINDOW_HOURS,
        "combination_window_hours": DEFAULT_COMBINATION_WINDOW_HOURS,
        "daily_alert_limit": DEFAULT_DAILY_ALERT_LIMIT,
        "allow_severity_upgrade_resend": True,
        "source": "backend_defaults",
    }


def test_notification_settings_api_returns_runtime_config(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_load_notification_settings(db_session) -> NotificationSettingsRead:
        captured["session"] = db_session
        return NotificationSettingsRead(
            realtime_sse=True,
            feishu_webhook=False,
            email=True,
            custom_webhook=False,
            source="database",
        )

    monkeypatch.setattr(
        "app.api.settings.load_notification_settings",
        fake_load_notification_settings,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/settings/notifications")

    assert response.status_code == 200
    assert captured["session"] is session
    assert response.json() == {
        "realtime_sse": True,
        "feishu_webhook": False,
        "email": True,
        "custom_webhook": False,
        "source": "database",
    }


def test_notification_settings_api_persists_updates(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_save_notification_settings(db_session, payload) -> NotificationSettingsRead:
        captured["session"] = db_session
        captured["payload"] = payload.model_dump(exclude_unset=True)
        return NotificationSettingsRead(
            realtime_sse=True,
            feishu_webhook=True,
            email=False,
            custom_webhook=True,
            source="database",
        )

    monkeypatch.setattr(
        "app.api.settings.save_notification_settings",
        fake_save_notification_settings,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.put(
        "/api/settings/notifications",
        json={"feishu_webhook": True, "custom_webhook": True},
    )

    assert response.status_code == 200
    assert captured["session"] is session
    assert captured["payload"] == {"feishu_webhook": True, "custom_webhook": True}
    assert response.json() == {
        "realtime_sse": True,
        "feishu_webhook": True,
        "email": False,
        "custom_webhook": True,
        "source": "database",
    }


def test_notification_settings_rejects_unknown_fields(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_save_notification_settings(db_session, payload) -> NotificationSettingsRead:
        raise AssertionError("save should not run for invalid payload")

    monkeypatch.setattr(
        "app.api.settings.save_notification_settings",
        fake_save_notification_settings,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.put(
        "/api/settings/notifications",
        json={"feishu_webhhook": True},
    )

    assert response.status_code == 422


def test_notification_settings_rejects_string_booleans(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_save_notification_settings(db_session, payload) -> NotificationSettingsRead:
        raise AssertionError("save should not run for invalid payload")

    monkeypatch.setattr(
        "app.api.settings.save_notification_settings",
        fake_save_notification_settings,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.put(
        "/api/settings/notifications",
        json={"realtime_sse": "false"},
    )

    assert response.status_code == 422


def test_llm_provider_settings_api_uses_env_runtime(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_active_config(*, session):
        return None

    monkeypatch.setattr("app.api.settings.get_active_llm_config", fake_active_config)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(xai_api_key="xai-test", _env_file=None),
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/settings/llm-providers")

    assert response.status_code == 200
    rows = {row["provider"]: row for row in response.json()}
    assert rows["xai"] == {
        "provider": "xai",
        "name": "xAI Grok",
        "model": "grok-4.3",
        "configured": True,
        "active": True,
        "source": "environment",
        "status": "active",
        "reason": None,
    }
    assert rows["openai"]["configured"] is False
    assert rows["openai"]["status"] == "unconfigured"
    assert rows["openai"]["reason"] == "OPENAI_API_KEY is not configured"


def test_llm_provider_settings_api_marks_database_route_active(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_active_config(*, session):
        return LLMProviderConfig(
            provider="deepseek",
            api_key="db-secret",
            model="deepseek-reasoner",
            base_url="https://db.example/v1",
        )

    monkeypatch.setattr("app.api.settings.get_active_llm_config", fake_active_config)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(xai_api_key="xai-test", _env_file=None),
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/settings/llm-providers")

    assert response.status_code == 200
    rows = {row["provider"]: row for row in response.json()}
    assert rows["deepseek"]["active"] is True
    assert rows["deepseek"]["source"] == "database"
    assert rows["deepseek"]["model"] == "deepseek-reasoner"
    assert rows["xai"]["active"] is False
    assert rows["xai"]["status"] == "configured"
