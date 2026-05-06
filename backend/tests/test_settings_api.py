from fastapi.testclient import TestClient

from app.api.settings import NotificationSettingsRead
from app.core.database import get_db
from app.main import create_app
from app.services.alert_agent.dedup import (
    DEFAULT_COMBINATION_WINDOW_HOURS,
    DEFAULT_DAILY_ALERT_LIMIT,
    DEFAULT_REPEAT_WINDOW_HOURS,
)


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
