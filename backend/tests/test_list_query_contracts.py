from fastapi.testclient import TestClient

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
