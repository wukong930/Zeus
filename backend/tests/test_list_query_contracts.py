from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.alerts import _alerts_statement
from app.api.arbitration import _human_decisions_statement
from app.api.drift import _drift_metrics_statement
from app.api.learning import _learning_hypotheses_statement
from app.api.news_events import _news_events_statement
from app.api.positions import _positions_statement
from app.api.recommendations import _recommendations_statement
from app.api.shadow import _shadow_runs_statement, _shadow_signal_count_statement
from app.api.strategies import _strategies_statement
from app.main import create_app


def test_status_filter_queries_are_bounded() -> None:
    client = TestClient(create_app())
    oversized = "x" * 21

    for path in (
        "/api/alerts",
        "/api/positions",
        "/api/recommendations",
        "/api/strategies",
    ):
        response = client.get(f"{path}?status_filter={oversized}")

        assert response.status_code == 422


def test_recommendation_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/recommendations?before=not-a-date")

    assert response.status_code == 422


def test_alert_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/alerts?before=not-a-date")

    assert response.status_code == 422


def test_position_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/positions?before=not-a-date")

    assert response.status_code == 422


def test_news_events_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/news-events?before=not-a-date")

    assert response.status_code == 422


def test_learning_hypotheses_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/learning/hypotheses?before=not-a-date")

    assert response.status_code == 422


def test_shadow_runs_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/shadow/runs?before=not-a-date")

    assert response.status_code == 422


def test_drift_metrics_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/drift/metrics?before=not-a-date")

    assert response.status_code == 422


def test_human_decisions_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/arbitration/decisions?before=not-a-date")

    assert response.status_code == 422

    response = client.get("/api/arbitration/decisions?decision=publish")
    assert response.status_code == 422


def test_strategies_list_rejects_invalid_cursor() -> None:
    client = TestClient(create_app())

    response = client.get("/api/strategies?before=not-a-date")

    assert response.status_code == 422


def test_alert_category_query_is_bounded() -> None:
    client = TestClient(create_app())

    response = client.get(f"/api/alerts?category={'x' * 21}")

    assert response.status_code == 422


def test_alert_queries_reject_unbounded_or_unknown_filters() -> None:
    client = TestClient(create_app())

    response = client.get("/api/alerts?severity=urgent")
    assert response.status_code == 422

    response = client.get(f"/api/alerts?symbol={'S' * 33}")
    assert response.status_code == 422

    response = client.get(f"/api/alerts?q={'q' * 121}")
    assert response.status_code == 422


def test_alerts_statement_pushes_filters_to_database() -> None:
    sql = _compile_postgres(
        _alerts_statement(
            status_filter="active",
            category="rubber",
            severity="critical,high",
            symbol="ru",
            human_action_required=True,
            adversarial_passed=False,
            q="橡胶",
            limit=50,
        )
    )

    assert "alerts.status =" in sql
    assert "alerts.category =" in sql
    assert "alerts.severity IN" in sql
    assert "alerts.related_assets" in sql
    assert "alerts.human_action_required IS true" in sql
    assert "alerts.adversarial_passed IS false" in sql
    assert "ILIKE" in sql
    assert "LIMIT" in sql


def test_alerts_short_query_matches_symbol_without_broad_text_scan() -> None:
    sql = _compile_postgres(
        _alerts_statement(
            status_filter=None,
            category=None,
            severity=None,
            symbol=None,
            human_action_required=None,
            adversarial_passed=None,
            q="I",
            limit=20,
        )
    )

    assert "alerts.related_assets" in sql
    assert "ILIKE" not in sql


def test_alerts_statement_excludes_expired_by_default() -> None:
    sql = _compile_postgres(
        _alerts_statement(
            status_filter=None,
            category=None,
            severity=None,
            symbol=None,
            human_action_required=True,
            adversarial_passed=None,
            q=None,
            limit=20,
        )
    )

    assert "alerts.expires_at IS NULL" in sql
    assert "alerts.expires_at >" in sql


def test_alerts_statement_can_include_expired_for_audit_views() -> None:
    sql = _compile_postgres(
        _alerts_statement(
            status_filter=None,
            category=None,
            severity=None,
            symbol=None,
            human_action_required=True,
            adversarial_passed=None,
            q=None,
            limit=20,
            include_expired=True,
        )
    )

    assert "alerts.expires_at IS NULL" not in sql
    assert "alerts.expires_at >" not in sql


def test_alerts_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _alerts_statement(
            status_filter="active",
            category=None,
            severity=None,
            symbol=None,
            human_action_required=None,
            adversarial_passed=None,
            q=None,
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
            include_expired=True,
        )
    )

    assert "alerts.status =" in sql
    assert "alerts.triggered_at <" in sql
    assert "ORDER BY alerts.triggered_at DESC, alerts.id DESC" in sql
    assert "LIMIT" in sql


def test_recommendations_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _recommendations_statement(
            status_filter="pending",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "recommendations.status =" in sql
    assert "recommendations.created_at <" in sql
    assert "ORDER BY recommendations.created_at DESC, recommendations.id DESC" in sql
    assert "LIMIT" in sql


def test_positions_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _positions_statement(
            status_filter="open",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "positions.status =" in sql
    assert "positions.opened_at <" in sql
    assert "ORDER BY positions.opened_at DESC, positions.id DESC" in sql
    assert "LIMIT" in sql


def test_news_events_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _news_events_statement(
            source="gdelt",
            symbol="sc",
            event_type="geopolitical",
            direction="bullish",
            min_severity=3,
            verification_status="cross_verified",
            q="原油",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "news_events.source =" in sql
    assert "news_events.affected_symbols" in sql
    assert "news_events.event_type =" in sql
    assert "news_events.direction =" in sql
    assert "news_events.severity >=" in sql
    assert "news_events.verification_status =" in sql
    assert "news_events.published_at <" in sql
    assert "ORDER BY news_events.published_at DESC, news_events.id DESC" in sql
    assert "LIMIT" in sql


def test_learning_hypotheses_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _learning_hypotheses_statement(
            status_filter="shadow_testing",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "learning_hypotheses.status =" in sql
    assert "learning_hypotheses.created_at <" in sql
    assert "ORDER BY learning_hypotheses.created_at DESC, learning_hypotheses.id DESC" in sql
    assert "LIMIT" in sql


def test_contract_symbol_query_is_bounded() -> None:
    client = TestClient(create_app())

    response = client.get(f"/api/contracts?symbol={'S' * 33}")

    assert response.status_code == 422


def test_shadow_query_strings_are_bounded() -> None:
    client = TestClient(create_app())

    response = client.post(f"/api/shadow/applications/initial?created_by={'x' * 81}")
    assert response.status_code == 422

    response = client.get(f"/api/shadow/calibration?signal_type={'x' * 31}")
    assert response.status_code == 422

    response = client.post(f"/api/shadow/calibration/reviews?category={'x' * 31}")
    assert response.status_code == 422

    response = client.get(f"/api/shadow/runs?status_filter={'x' * 21}")
    assert response.status_code == 422


def test_shadow_runs_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _shadow_runs_statement(
            status_filter="active",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "shadow_runs.status =" in sql
    assert "shadow_runs.started_at <" in sql
    assert "ORDER BY shadow_runs.started_at DESC, shadow_runs.id DESC" in sql
    assert "LIMIT" in sql


def test_shadow_signal_count_statement_uses_database_count() -> None:
    sql = _compile_postgres(_shadow_signal_count_statement("00000000-0000-0000-0000-000000000001"))

    assert "count(*)" in sql.lower()
    assert "shadow_signals.shadow_run_id =" in sql


def test_drift_metrics_statement_uses_filters_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _drift_metrics_statement(
            metric_type="feature_distribution",
            category="rubber",
            drift_severity="yellow",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "drift_metrics.metric_type =" in sql
    assert "drift_metrics.category =" in sql
    assert "drift_metrics.drift_severity =" in sql
    assert "drift_metrics.computed_at <" in sql
    assert "ORDER BY drift_metrics.computed_at DESC, drift_metrics.id DESC" in sql
    assert "LIMIT" in sql


def test_human_decisions_statement_uses_filters_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _human_decisions_statement(
            alert_id=uuid4(),
            signal_track_id=uuid4(),
            decision="approve",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "human_decisions.alert_id =" in sql
    assert "human_decisions.signal_track_id =" in sql
    assert "human_decisions.decision =" in sql
    assert "human_decisions.created_at <" in sql
    assert "ORDER BY human_decisions.created_at DESC, human_decisions.id DESC" in sql
    assert "LIMIT" in sql


def test_strategies_statement_uses_keyset_cursor_and_stable_order() -> None:
    sql = _compile_postgres(
        _strategies_statement(
            status_filter="active",
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            limit=20,
        )
    )

    assert "strategies.status =" in sql
    assert "strategies.created_at <" in sql
    assert "ORDER BY strategies.created_at DESC, strategies.id DESC" in sql
    assert "LIMIT" in sql


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
