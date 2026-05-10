from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.news_events import NewsEvent
from app.services.event_intelligence import build_event_intelligence_from_news


def test_build_event_intelligence_from_news_maps_weather_to_rubber_impacts() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    news = NewsEvent(
        id=uuid4(),
        source="gdelt",
        raw_url="https://example.com/rubber-weather",
        title="Thailand rainfall anomaly disrupts natural rubber tapping",
        summary="Southeast Asia heavy rainfall and flood risk may reduce latex output.",
        content_text="Rubber supply faces weather disruption across Thailand and Vietnam.",
        published_at=now,
        event_type="weather",
        affected_symbols=["RU", "NR"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        llm_confidence=0.9,
        source_count=3,
        verification_status="cross_verified",
        requires_manual_confirmation=False,
        dedup_hash="rubber-weather-1",
        extraction_payload={"entities": ["Thailand", "Vietnam"]},
    )

    event, links = build_event_intelligence_from_news(news, now=now)

    assert event.source_type == "news_event"
    assert event.status == "shadow_review"
    assert event.requires_manual_confirmation is False
    assert event.symbols == ("NR", "RU")
    assert "weather" in event.mechanisms
    assert "supply" in event.mechanisms
    assert "southeast_asia_rubber" in event.regions
    assert links
    assert {link.symbol for link in links} == {"RU", "NR"}
    assert all(link.direction == "bullish" for link in links)
    assert max(link.impact_score for link in links) > 70


def test_build_event_intelligence_requires_human_review_for_weak_single_source() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    news = NewsEvent(
        id=uuid4(),
        source="social",
        raw_url=None,
        title="Unverified aircraft carrier rumor near Iran",
        summary="Single-source geopolitical rumor mentions Iran and crude oil routes.",
        content_text=None,
        published_at=now,
        event_type="geopolitical",
        affected_symbols=["SC"],
        direction="unclear",
        severity=5,
        time_horizon="immediate",
        llm_confidence=0.56,
        source_count=1,
        verification_status="single_source",
        requires_manual_confirmation=False,
        dedup_hash="carrier-rumor-1",
        extraction_payload={},
    )

    event, links = build_event_intelligence_from_news(news, now=now)

    assert event.status == "human_review"
    assert event.requires_manual_confirmation is True
    assert event.source_reliability < 0.6
    assert "geopolitical" in event.mechanisms
    assert links[0].symbol == "SC"
    assert links[0].status == "human_review"
    assert links[0].direction == "watch"


def test_event_intelligence_api_rejects_invalid_filters() -> None:
    client = TestClient(create_app())

    response = client.get("/api/event-intelligence?status=published")

    assert response.status_code == 422
