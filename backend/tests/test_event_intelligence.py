from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.event_intelligence import EventImpactLink, EventIntelligenceAuditLog, EventIntelligenceItem
from app.models.news_events import NewsEvent
from app.services.event_intelligence import (
    apply_event_intelligence_decision,
    build_event_intelligence_from_news,
    evaluate_event_intelligence_quality,
    parse_semantic_extraction,
    summarize_event_intelligence_quality,
)
from app.services.event_intelligence.eval_cases import EVENT_INTELLIGENCE_EVAL_CASES


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


def test_event_intelligence_decision_api_rejects_invalid_decision() -> None:
    client = TestClient(create_app())

    response = client.post(
        f"/api/event-intelligence/{uuid4()}/decision",
        json={"decision": "publish"},
    )

    assert response.status_code == 422


def test_event_intelligence_eval_cases_api_returns_samples() -> None:
    client = TestClient(create_app())

    response = client.get("/api/event-intelligence/eval-cases")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 5
    assert payload[0]["expected_symbols"]


async def test_apply_event_intelligence_decision_records_audit() -> None:
    event_id = uuid4()
    event_item = EventIntelligenceItem(
        id=event_id,
        source_type="news_event",
        source_id=str(uuid4()),
        title="Carrier rumor",
        summary="Single-source report needs confirmation.",
        event_type="geopolitical",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=[],
        symbols=["SC"],
        regions=["middle_east_crude"],
        mechanisms=["geopolitical"],
        evidence=[],
        counterevidence=[],
        confidence=0.62,
        impact_score=62,
        status="human_review",
        requires_manual_confirmation=True,
        source_reliability=0.45,
        freshness_score=1,
        source_payload={},
    )
    session = FakeDecisionSession(event_item)

    updated, audit = await apply_event_intelligence_decision(
        session,  # type: ignore[arg-type]
        event_id,
        decision="confirm",
        decided_by="operator",
        note="Verified with secondary source.",
        confidence_override=0.8,
    )

    assert updated.status == "confirmed"
    assert updated.requires_manual_confirmation is False
    assert updated.confidence == 0.8
    assert isinstance(audit, EventIntelligenceAuditLog)
    assert audit.action == "decision.confirm"
    assert audit.before_status == "human_review"
    assert audit.after_status == "confirmed"
    assert audit.actor == "operator"
    assert session.flush_count == 1
    assert session.execute_count == 1


def test_parse_semantic_extraction_normalizes_and_filters_hypotheses() -> None:
    semantic = parse_semantic_extraction(
        """
        {
          "direction": "mixed",
          "confidence": 0.82,
          "symbols": ["sc", "xx"],
          "mechanisms": ["geopolitical", "unknown"],
          "hypotheses": [
            {
              "symbol": "sc",
              "region_id": "middle_east_crude",
              "mechanism": "geopolitical",
              "direction": "bullish",
              "confidence": 0.86,
              "horizon": "short",
              "rationale": "Hormuz risk premium may affect crude.",
              "evidence": ["Carrier group reportedly moved toward Iran."],
              "counterevidence": ["Single-source report."]
            },
            {
              "symbol": "xx",
              "mechanism": "weather",
              "direction": "bullish",
              "confidence": 0.9
            }
          ]
        }
        """,
        model="test-model",
    )

    assert semantic.model == "test-model"
    assert semantic.symbols == ["SC"]
    assert semantic.mechanisms == ["geopolitical"]
    assert len(semantic.hypotheses) == 1
    assert semantic.hypotheses[0].symbol == "SC"


def test_build_event_intelligence_merges_semantic_multi_commodity_hypotheses() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    news = NewsEvent(
        id=uuid4(),
        source="policy",
        raw_url=None,
        title="Tariff threat hits industrial commodities",
        summary="New trade tariff threat pressures copper sentiment while steel cost risk rises.",
        content_text="Trump tariff post triggers risk-off selling in copper and mixed ferrous risk.",
        published_at=now,
        event_type="policy",
        affected_symbols=[],
        direction="unclear",
        severity=3,
        time_horizon="short",
        llm_confidence=0.72,
        source_count=2,
        verification_status="multi_source",
        requires_manual_confirmation=False,
        dedup_hash="tariff-policy-1",
        extraction_payload={},
    )
    semantic = parse_semantic_extraction(
        """
        {
          "direction": "mixed",
          "confidence": 0.8,
          "symbols": ["CU", "RB"],
          "mechanisms": ["policy", "risk_sentiment", "cost"],
          "hypotheses": [
            {
              "symbol": "CU",
              "region_id": "global_base_metals",
              "mechanism": "risk_sentiment",
              "direction": "bearish",
              "confidence": 0.84,
              "horizon": "immediate",
              "rationale": "Tariff risk can drive risk-off selling in copper."
            },
            {
              "symbol": "RB",
              "region_id": "north_china_ferrous",
              "mechanism": "cost",
              "direction": "mixed",
              "confidence": 0.71,
              "horizon": "short",
              "rationale": "Ferrous cost-chain pressure is mixed with demand uncertainty."
            }
          ]
        }
        """
    )

    event, links = build_event_intelligence_from_news(news, now=now, semantic=semantic)

    assert event.source_payload["semantic_used"] is True
    assert event.symbols == ("CU", "RB")
    assert "risk_sentiment" in event.mechanisms
    link_by_scope = {(link.symbol, link.mechanism): link for link in links}
    assert link_by_scope[("CU", "risk_sentiment")].direction == "bearish"
    assert link_by_scope[("RB", "cost")].direction == "mixed"


def test_event_intelligence_eval_cases_cover_required_scenarios() -> None:
    case_ids = {case.id for case in EVENT_INTELLIGENCE_EVAL_CASES}

    assert {
        "rubber-weather-el-nino",
        "carrier-iran-crude",
        "tariff-ferrous-base-metals",
        "port-flood-logistics",
    }.issubset(case_ids)


def test_event_intelligence_quality_gate_marks_confirmed_evidence_as_decision_grade() -> None:
    event_id = uuid4()
    event_item = EventIntelligenceItem(
        id=event_id,
        source_type="news_event",
        source_id=str(uuid4()),
        title="Verified rubber weather disruption",
        summary="Multi-source rainfall anomaly affects rubber tapping.",
        event_type="weather",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=["Thailand"],
        symbols=["RU"],
        regions=["southeast_asia_rubber"],
        mechanisms=["weather", "supply"],
        evidence=["Rainfall anomaly report", "Station precipitation percentile"],
        counterevidence=["Forecast path may shift"],
        confidence=0.88,
        impact_score=88,
        status="confirmed",
        requires_manual_confirmation=False,
        source_reliability=0.82,
        freshness_score=0.96,
        source_payload={},
    )
    link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_id,
        symbol="RU",
        region_id="southeast_asia_rubber",
        mechanism="weather",
        direction="bullish",
        confidence=0.84,
        impact_score=84,
        horizon="short",
        rationale="Rainfall may reduce tapping days and tighten near-end supply.",
        evidence=["Rainfall anomaly report"],
        counterevidence=["Forecast path may shift"],
        status="confirmed",
    )

    report = evaluate_event_intelligence_quality(event_item, [link])
    summary = summarize_event_intelligence_quality([report])

    assert report.status == "decision_grade"
    assert report.decision_grade is True
    assert report.passed_gate is True
    assert report.link_reports[0].passed_gate is True
    assert summary.decision_grade == 1
    assert summary.average_score >= 82


def test_event_intelligence_quality_gate_blocks_missing_evidence_and_links() -> None:
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="social",
        source_id=str(uuid4()),
        title="Single source crude rumor",
        summary="Unverified rumor needs review.",
        event_type="geopolitical",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=[],
        symbols=["SC"],
        regions=["middle_east_crude"],
        mechanisms=["geopolitical"],
        evidence=[],
        counterevidence=[],
        confidence=0.5,
        impact_score=50,
        status="human_review",
        requires_manual_confirmation=True,
        source_reliability=0.35,
        freshness_score=1,
        source_payload={},
    )

    report = evaluate_event_intelligence_quality(event_item, [])

    assert report.status == "blocked"
    assert report.passed_gate is False
    assert {issue.code for issue in report.issues} >= {
        "missing_evidence",
        "missing_impact_links",
        "manual_review_required",
    }


def test_event_intelligence_quality_gate_keeps_human_review_as_review_not_blocked() -> None:
    event_id = uuid4()
    event_item = EventIntelligenceItem(
        id=event_id,
        source_type="news_event",
        source_id=str(uuid4()),
        title="Rubber policy report needs review",
        summary="Single-source policy event has evidence but awaits confirmation.",
        event_type="policy",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=[],
        symbols=["RU"],
        regions=["southeast_asia_rubber"],
        mechanisms=["policy"],
        evidence=["Policy headline"],
        counterevidence=["Awaiting independent confirmation"],
        confidence=0.58,
        impact_score=58,
        status="human_review",
        requires_manual_confirmation=True,
        source_reliability=0.45,
        freshness_score=1,
        source_payload={},
    )
    link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_id,
        symbol="RU",
        region_id="southeast_asia_rubber",
        mechanism="policy",
        direction="watch",
        confidence=0.57,
        impact_score=57,
        horizon="short",
        rationale="Policy report may affect import expectations if confirmed.",
        evidence=["Policy headline"],
        counterevidence=["Awaiting independent confirmation"],
        status="human_review",
    )

    report = evaluate_event_intelligence_quality(event_item, [link])

    assert report.status == "review"
    assert "impact_links_need_review" in {issue.code for issue in report.issues}
    assert "no_usable_impact_links" not in {issue.code for issue in report.issues}


class FakeDecisionSession:
    def __init__(self, event_item: EventIntelligenceItem) -> None:
        self.event_item = event_item
        self.rows: list[object] = []
        self.flush_count = 0
        self.execute_count = 0

    async def get(self, model, key):
        if model is EventIntelligenceItem and key == self.event_item.id:
            return self.event_item
        return None

    async def execute(self, _):
        self.execute_count += 1

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1
