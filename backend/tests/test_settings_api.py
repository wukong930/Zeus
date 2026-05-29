from datetime import date

from fastapi.testclient import TestClient

from app.api.settings import (
    AdversarialRuntimeSettingsRead,
    LLMProviderSettingsRead,
    NotificationSettingsRead,
)
from app.core.config import Settings
from app.core.database import get_db
from app.main import create_app
from app.services.alert_agent.dedup import (
    DEFAULT_COMBINATION_WINDOW_HOURS,
    DEFAULT_DAILY_ALERT_LIMIT,
    DEFAULT_REPEAT_WINDOW_HOURS,
)
from app.services.llm.cost_tracker import LLMUsageSummary
from app.services.llm.types import LLMProviderConfig


class FakeDataSourceStatus:
    def to_dict(self) -> dict:
        return {
            "id": "gdelt",
            "name": "GDELT DOC 2.0",
            "category": "news_events",
            "enabled": True,
            "configured": True,
            "requires_key": False,
            "free_tier": "free_no_key",
            "status": "ready",
            "note": "news",
        }


class FakeScheduler:
    def list_jobs(self) -> list[dict]:
        return [{"id": "news", "name": "News ingest", "status": "ok"}]

    def health_summary(self) -> dict:
        return {
            "total_jobs": 1,
            "enabled_jobs": 1,
            "degraded_jobs": [],
            "warning_jobs": [],
            "unconfigured_jobs": [],
            "planned_unconfigured_jobs": [],
            "handler_coverage": {
                "total": 1,
                "registered": 1,
                "missing": 0,
                "unconfigured": 0,
                "planned": 0,
            },
            "last_activity": None,
            "jobs": [],
        }


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


def test_settings_snapshot_collapses_settings_page_runtime_calls(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_monthly_usage_summary(db_session, *, module, period_start, period_end):
        captured["usage_session"] = db_session
        captured["usage_module"] = module
        captured["usage_period"] = (period_start, period_end)
        return LLMUsageSummary(
            module=module,
            period_start=period_start,
            period_end=period_end,
            calls=3,
            cache_hits=1,
            estimated_cost_usd=0.42,
            input_tokens=100,
            output_tokens=50,
        )

    async def fake_load_llm_provider_settings(db_session):
        captured["provider_session"] = db_session
        return [
            LLMProviderSettingsRead(
                provider="xai",
                name="xAI Grok",
                model="grok-4.3",
                configured=True,
                active=True,
                source="environment",
                status="active",
            )
        ]

    async def fake_load_notification_settings(db_session) -> NotificationSettingsRead:
        captured["notification_session"] = db_session
        return NotificationSettingsRead(
            realtime_sse=True,
            feishu_webhook=True,
            email=False,
            custom_webhook=False,
            source="database",
        )

    async def fake_load_adversarial_runtime_config(db_session) -> AdversarialRuntimeSettingsRead:
        captured["adversarial_session"] = db_session
        return AdversarialRuntimeSettingsRead(
            warmup_enabled=False,
            mode="enforcing",
            historical_combo_mode="sample_based_enforcing",
            production_effect="may_suppress_signals",
            source="database",
        )

    monkeypatch.setattr("app.api.settings.data_source_statuses", lambda: [FakeDataSourceStatus()])
    monkeypatch.setattr("app.api.settings.get_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr("app.api.settings.monthly_usage_summary", fake_monthly_usage_summary)
    monkeypatch.setattr(
        "app.api.settings.load_llm_provider_settings",
        fake_load_llm_provider_settings,
    )
    monkeypatch.setattr(
        "app.api.settings.load_notification_settings",
        fake_load_notification_settings,
    )
    monkeypatch.setattr(
        "app.api.settings.load_adversarial_runtime_config",
        fake_load_adversarial_runtime_config,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get(
        "/api/settings/snapshot",
        params={"module": " Event_Intelligence ", "month": "2026-05-01"},
    )

    assert response.status_code == 200
    assert captured["usage_session"] is session
    assert captured["provider_session"] is session
    assert captured["notification_session"] is session
    assert captured["adversarial_session"] is session
    assert captured["usage_module"] == "event_intelligence"
    assert captured["usage_period"] == (date(2026, 5, 1), date(2026, 6, 1))
    payload = response.json()
    assert payload["data_sources"][0]["id"] == "gdelt"
    assert payload["scheduler"]["health"]["handler_coverage"]["registered"] == 1
    assert payload["llm_usage"]["calls"] == 3
    assert payload["llm_providers"][0]["active"] is True
    assert payload["alert_dedup"]["daily_alert_limit"] == DEFAULT_DAILY_ALERT_LIMIT
    assert payload["notifications"]["feishu_webhook"] is True
    assert payload["adversarial_runtime"]["mode"] == "enforcing"


def test_settings_snapshot_bounds_module_query() -> None:
    client = TestClient(create_app())

    response = client.get("/api/settings/snapshot", params={"module": "x" * 41})

    assert response.status_code == 422


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


def test_adversarial_runtime_settings_api_returns_runtime_config(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_load_adversarial_runtime_config(db_session) -> AdversarialRuntimeSettingsRead:
        captured["session"] = db_session
        return AdversarialRuntimeSettingsRead(
            warmup_enabled=True,
            mode="warmup",
            historical_combo_mode="informational",
            production_effect="observe_only",
            source="database",
        )

    monkeypatch.setattr(
        "app.api.settings.load_adversarial_runtime_config",
        fake_load_adversarial_runtime_config,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/settings/adversarial-runtime")

    assert response.status_code == 200
    assert captured["session"] is session
    assert response.json() == {
        "warmup_enabled": True,
        "mode": "warmup",
        "historical_combo_mode": "informational",
        "production_effect": "observe_only",
        "source": "database",
    }


def test_adversarial_runtime_settings_api_persists_manual_override(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_save_adversarial_runtime_config(
        db_session,
        *,
        warmup_enabled,
    ) -> AdversarialRuntimeSettingsRead:
        captured["session"] = db_session
        captured["warmup_enabled"] = warmup_enabled
        return AdversarialRuntimeSettingsRead(
            warmup_enabled=False,
            mode="enforcing",
            historical_combo_mode="sample_based_enforcing",
            production_effect="may_suppress_signals",
            source="database",
        )

    monkeypatch.setattr(
        "app.api.settings.save_adversarial_runtime_config",
        fake_save_adversarial_runtime_config,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.put(
        "/api/settings/adversarial-runtime",
        json={"warmup_enabled": False},
    )

    assert response.status_code == 200
    assert captured["session"] is session
    assert captured["warmup_enabled"] is False
    assert response.json()["mode"] == "enforcing"
    assert response.json()["production_effect"] == "may_suppress_signals"


def test_adversarial_runtime_settings_rejects_string_booleans(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_save_adversarial_runtime_config(db_session, *, warmup_enabled):
        raise AssertionError("save should not run for invalid payload")

    monkeypatch.setattr(
        "app.api.settings.save_adversarial_runtime_config",
        fake_save_adversarial_runtime_config,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.put(
        "/api/settings/adversarial-runtime",
        json={"warmup_enabled": "false"},
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
