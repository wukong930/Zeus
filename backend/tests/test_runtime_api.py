from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.runtime import (
    RuntimeCalibrationSnapshot,
    RuntimeDriftNotification,
    RuntimeDriftSnapshot,
    RuntimeHeartbeatSnapshot,
    RuntimeSchedulerSnapshot,
    _active_signal_summary_statement,
    _calibration_samples_statement,
    _clear_runtime_heartbeat_cache,
)
from app.core.database import get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_runtime_heartbeat_cache_between_tests():
    _clear_runtime_heartbeat_cache()
    yield
    _clear_runtime_heartbeat_cache()


def test_runtime_heartbeat_endpoint_uses_lightweight_summaries(monkeypatch) -> None:
    session = object()
    latest_signal_at = datetime(2026, 5, 18, 8, 0, tzinfo=timezone.utc)
    latest_drift_at = datetime(2026, 5, 18, 7, 30, tzinfo=timezone.utc)
    captured: dict[str, object] = {}

    async def fake_db():
        yield session

    async def fake_active_signal_summary(db_session, *, now):
        captured["active_session"] = db_session
        captured["active_now"] = now
        return 9, latest_signal_at

    async def fake_drift_runtime_snapshot(db_session):
        captured["drift_session"] = db_session
        return RuntimeDriftSnapshot(
            status="green",
            latest_at=latest_drift_at,
            notification=RuntimeDriftNotification(
                level="none",
                title="Drift 正常",
                should_notify=False,
            ),
        )

    async def fake_calibration_samples(db_session, *, now, lookback_days):
        captured["calibration_session"] = db_session
        captured["calibration_now"] = now
        captured["lookback_days"] = lookback_days
        return 36

    class FakeScheduler:
        def health_summary(self):
            return {
                "degraded_jobs": [],
                "warning_jobs": ["drift-monitor"],
                "unconfigured_jobs": [],
                "last_activity": "2026-05-18T07:45:00+00:00",
                "handler_coverage": {
                    "total": 12,
                    "registered": 12,
                    "missing": 0,
                    "unconfigured": 0,
                    "planned": 0,
                },
            }

    monkeypatch.setattr("app.api.runtime._active_signal_summary", fake_active_signal_summary)
    monkeypatch.setattr("app.api.runtime._drift_runtime_snapshot", fake_drift_runtime_snapshot)
    monkeypatch.setattr("app.api.runtime._calibration_samples", fake_calibration_samples)
    monkeypatch.setattr("app.api.runtime.get_scheduler", lambda: FakeScheduler())

    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/runtime/heartbeat?calibration_lookback_days=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_signals"] == 9
    assert _parse_api_datetime(payload["latest_at"]) == latest_signal_at
    assert payload["drift"]["status"] == "green"
    assert payload["calibration"] == {"samples": 36, "lookback_days": 30}
    assert payload["scheduler"]["warning_jobs"] == ["drift-monitor"]
    assert payload["status"] == "scheduler_degraded"
    assert captured["active_session"] is session
    assert captured["drift_session"] is session
    assert captured["calibration_session"] is session
    assert captured["lookback_days"] == 30


def test_runtime_heartbeat_endpoint_reuses_short_ttl_cache(monkeypatch) -> None:
    session = object()
    calls = {"count": 0}

    async def fake_db():
        yield session

    async def fake_build_runtime_heartbeat(db_session, *, calibration_lookback_days):
        calls["count"] += 1
        assert db_session is session
        assert calibration_lookback_days == 30
        generated_at = datetime(2026, 5, 18, 8, 0, calls["count"], tzinfo=timezone.utc)
        return RuntimeHeartbeatSnapshot(
            generated_at=generated_at,
            latest_at=generated_at,
            active_signals=calls["count"],
            drift=RuntimeDriftSnapshot(
                status="green",
                latest_at=generated_at,
                notification=RuntimeDriftNotification(
                    level="none",
                    title="Drift 正常",
                    should_notify=False,
                ),
            ),
            calibration=RuntimeCalibrationSnapshot(
                samples=10 + calls["count"],
                lookback_days=30,
            ),
            scheduler=RuntimeSchedulerSnapshot(
                degraded_jobs=[],
                warning_jobs=[],
                unconfigured_jobs=[],
                last_activity=None,
                handler_coverage={"total": 1, "registered": 1},
            ),
            status="running",
        )

    monkeypatch.setattr("app.api.runtime.build_runtime_heartbeat", fake_build_runtime_heartbeat)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    first = client.get("/api/runtime/heartbeat?calibration_lookback_days=30")
    second = client.get("/api/runtime/heartbeat?calibration_lookback_days=30")
    refreshed = client.get("/api/runtime/heartbeat?calibration_lookback_days=30&refresh=true")

    assert first.status_code == 200
    assert second.status_code == 200
    assert refreshed.status_code == 200
    assert calls["count"] == 2
    assert first.json()["generated_at"] == second.json()["generated_at"]
    assert first.json()["calibration"]["samples"] == 11
    assert refreshed.json()["calibration"]["samples"] == 12


def test_runtime_heartbeat_queries_are_index_friendly() -> None:
    now = datetime(2026, 5, 18, 8, 0, tzinfo=timezone.utc)

    active_sql = _compile_postgres(_active_signal_summary_statement(now=now))
    calibration_sql = _compile_postgres(
        _calibration_samples_statement(now=now, lookback_days=180)
    )

    assert "count(signal_track.id)" in active_sql
    assert "max(signal_track.created_at)" in active_sql
    assert "signal_track.created_at >=" in active_sql
    assert "ORDER BY" not in active_sql
    assert "count(signal_track.id)" in calibration_sql
    assert "signal_track.outcome IN" in calibration_sql
    assert "signal_track.created_at >=" in calibration_sql
    assert "signal_track.created_at <=" in calibration_sql


def test_runtime_heartbeat_rejects_oversized_lookback() -> None:
    client = TestClient(create_app())

    response = client.get("/api/runtime/heartbeat?calibration_lookback_days=731")

    assert response.status_code == 422


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
