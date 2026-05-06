from fastapi.testclient import TestClient

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
