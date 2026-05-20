from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.news_events import _news_events_statement
from app.main import create_app


def test_news_events_api_rejects_unbounded_filters() -> None:
    client = TestClient(create_app())

    response = client.get(f"/api/news-events?source={'s' * 51}")
    assert response.status_code == 422

    response = client.get(f"/api/news-events?symbol={'S' * 33}")
    assert response.status_code == 422

    response = client.get(f"/api/news-events?verification_status={'v' * 31}")
    assert response.status_code == 422

    response = client.get(f"/api/news-events?q={'q' * 121}")
    assert response.status_code == 422


def test_news_events_api_rejects_unknown_event_type_filter() -> None:
    client = TestClient(create_app())

    response = client.get("/api/news-events?event_type=unsupported")

    assert response.status_code == 422


def test_news_events_api_rejects_unknown_direction_filter() -> None:
    client = TestClient(create_app())

    response = client.get("/api/news-events?direction=sideways")

    assert response.status_code == 422


def test_news_events_statement_pushes_filters_to_database() -> None:
    sql = _compile_postgres(
        _news_events_statement(
            source="gdelt",
            symbol="ru",
            event_type="weather",
            direction="bullish",
            min_severity=3,
            verification_status="cross_verified",
            q="rubber",
            limit=50,
        )
    )

    assert "news_events.source =" in sql
    assert "news_events.affected_symbols" in sql
    assert "news_events.event_type =" in sql
    assert "news_events.direction =" in sql
    assert "news_events.severity >=" in sql
    assert "news_events.verification_status =" in sql
    assert "ILIKE" in sql
    assert "LIMIT" in sql


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
