from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.alerts import _alerts_statement
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


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
