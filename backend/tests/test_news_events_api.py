from fastapi.testclient import TestClient

from app.main import create_app


def test_news_events_api_rejects_unbounded_filters() -> None:
    client = TestClient(create_app())

    response = client.get(f"/api/news-events?source={'s' * 51}")
    assert response.status_code == 422

    response = client.get(f"/api/news-events?symbol={'S' * 33}")
    assert response.status_code == 422

    response = client.get(f"/api/news-events?verification_status={'v' * 31}")
    assert response.status_code == 422


def test_news_events_api_rejects_unknown_event_type_filter() -> None:
    client = TestClient(create_app())

    response = client.get("/api/news-events?event_type=unsupported")

    assert response.status_code == 422
