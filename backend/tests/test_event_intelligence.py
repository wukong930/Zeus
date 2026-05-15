from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.change_review_queue import ChangeReviewQueue
from app.main import create_app
from app.models.event_intelligence import EventImpactLink, EventIntelligenceAuditLog, EventIntelligenceItem
from app.models.industry_data import IndustryData
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack
from app.models.vector_chunks import VectorChunk
from app.services.event_intelligence import (
    apply_event_intelligence_decision,
    build_event_intelligence_from_news,
    enqueue_event_intelligence_review,
    event_intelligence_review_reasons,
    evaluate_event_intelligence_quality,
    parse_semantic_extraction,
    summarize_event_intelligence_quality,
    update_event_impact_link,
)
from app.services.event_intelligence.eval_cases import EVENT_INTELLIGENCE_EVAL_CASES
from app.services.event_intelligence.ingress import (
    market_signal_event_candidate,
    weather_event_candidates_from_industry_rows,
)


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


def test_weather_ingress_builds_event_candidate_from_runtime_and_baseline_rows() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    rows = [
        IndustryData(
            symbol="NR",
            data_type="weather_precip_7d",
            value=180,
            unit="mm",
            source="nasa_power:hat_yai",
            timestamp=now,
        ),
        IndustryData(
            symbol="NR",
            data_type="weather_baseline_precip_7d",
            value=80,
            unit="mm",
            source="nasa_power_baseline:hat_yai",
            timestamp=now,
        ),
        IndustryData(
            symbol="NR",
            data_type="weather_precip_pctile_7d",
            value=96,
            unit="pctile",
            source="nasa_power_baseline:hat_yai",
            timestamp=now,
        ),
    ]

    candidates = weather_event_candidates_from_industry_rows(rows, now=now)

    assert len(candidates) == 1
    event, links = candidates[0]
    assert event.source_type == "weather"
    assert event.source_id == "weather:southeast_asia_rubber:NR:2026-05-14"
    assert event.symbols == ["NR"]
    assert event.regions == ["southeast_asia_rubber"]
    assert event.mechanisms == ["weather", "supply", "logistics"]
    assert event.confidence >= 0.85
    assert {link.mechanism for link in links} == {"weather", "supply", "logistics"}
    assert all(link.region_id == "southeast_asia_rubber" for link in links)


def test_weather_ingress_ignores_non_anomalous_weather_rows() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    rows = [
        IndustryData(
            symbol="NR",
            data_type="weather_precip_7d",
            value=82,
            unit="mm",
            source="nasa_power:hat_yai",
            timestamp=now,
        ),
        IndustryData(
            symbol="NR",
            data_type="weather_baseline_precip_7d",
            value=80,
            unit="mm",
            source="nasa_power_baseline:hat_yai",
            timestamp=now,
        ),
    ]

    assert weather_event_candidates_from_industry_rows(rows, now=now) == []


def test_market_signal_ingress_maps_high_confidence_signal_to_event_scope() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    row = SignalTrack(
        id=uuid4(),
        signal_type="price_gap",
        category="rubber",
        confidence=0.81,
        z_score=2.4,
        regime="volatile",
        regime_at_emission="volatile",
        adversarial_passed=True,
        outcome="pending",
        created_at=now,
    )

    candidate = market_signal_event_candidate(row, now=now)

    assert candidate is not None
    event, links = candidate
    assert event.source_type == "market"
    assert event.source_id == str(row.id)
    assert event.event_type == "market"
    assert event.symbols == ["RU", "NR", "BR"]
    assert event.mechanisms == ["risk_sentiment"]
    assert event.confidence == 0.81
    assert {link.symbol for link in links} == {"RU", "NR", "BR"}
    assert all(link.direction == "watch" for link in links)


def test_market_signal_ingress_uses_translated_signal_labels() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    row = SignalTrack(
        id=uuid4(),
        signal_type="inventory_shock",
        category="rubber",
        confidence=0.78,
        outcome="pending",
        created_at=now,
    )

    candidate = market_signal_event_candidate(row, now=now)

    assert candidate is not None
    event, links = candidate
    assert event.title == "行情异常：库存冲击"
    assert event.summary == "橡胶板块出现库存冲击，进入事件智能候选链。"
    assert event.source_payload["signal_type_label"] == "库存冲击"
    assert "inventory_shock" not in event.title
    assert all("inventory_shock" not in link.rationale for link in links)
    assert all("库存冲击" in link.rationale for link in links)


def test_market_signal_ingress_skips_low_confidence_or_unmapped_category() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    low_confidence = SignalTrack(
        id=uuid4(),
        signal_type="momentum",
        category="rubber",
        confidence=0.4,
        outcome="pending",
        created_at=now,
    )
    unmapped = SignalTrack(
        id=uuid4(),
        signal_type="momentum",
        category="unknown",
        confidence=0.9,
        outcome="pending",
        created_at=now,
    )

    assert market_signal_event_candidate(low_confidence, now=now) is None
    assert market_signal_event_candidate(unmapped, now=now) is None


async def test_event_intelligence_review_queue_records_high_impact_uncertainty() -> None:
    event_id = uuid4()
    event_item = EventIntelligenceItem(
        id=event_id,
        source_type="news_event",
        source_id=str(uuid4()),
        title="Single source crude shipping rumor",
        summary="Unverified shipping route claim may affect crude risk premium.",
        event_type="geopolitical",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=["Iran"],
        symbols=["SC"],
        regions=["middle_east_crude"],
        mechanisms=["geopolitical"],
        evidence=["Single source headline"],
        counterevidence=["No secondary confirmation"],
        confidence=0.58,
        impact_score=82,
        status="human_review",
        requires_manual_confirmation=True,
        source_reliability=0.42,
        freshness_score=1,
        source_payload={"source_count": 1, "verification_status": "single_source"},
    )
    link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_id,
        symbol="SC",
        region_id="middle_east_crude",
        mechanism="geopolitical",
        direction="watch",
        confidence=0.58,
        impact_score=82,
        horizon="immediate",
        rationale="Needs confirmation before decision-grade use.",
        evidence=["Single source headline"],
        counterevidence=["No secondary confirmation"],
        status="human_review",
    )
    session = FakeReviewSession()

    reasons = event_intelligence_review_reasons(event_item, [link])
    review = await enqueue_event_intelligence_review(
        session,  # type: ignore[arg-type]
        event_item,
        [link],
        actor="test",
    )

    assert review is not None
    assert isinstance(review, ChangeReviewQueue)
    assert review.source == "event_intelligence"
    assert review.target_table == "event_intelligence_items"
    assert review.target_key == str(event_id)
    assert "high_impact_uncertain_event" in reasons
    assert "manual_confirmation_required" in review.proposed_change["review_reasons"]
    assert review.proposed_change["production_effect"] == "none"
    audits = [row for row in session.rows if isinstance(row, EventIntelligenceAuditLog)]
    assert audits[0].action == "review.queued"
    assert audits[0].payload["production_effect"] == "none"


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


def test_event_impact_link_update_api_rejects_invalid_confidence() -> None:
    client = TestClient(create_app())

    response = client.patch(
        f"/api/event-intelligence/impact-links/{uuid4()}",
        json={"confidence": 1.5},
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
    reviews = [row for row in session.rows if isinstance(row, ChangeReviewQueue)]
    chunks = [row for row in session.rows if isinstance(row, VectorChunk)]
    assert reviews[0].status == "approved"
    assert reviews[0].reviewed_by == "operator"
    assert chunks[0].chunk_type == "event_intelligence_review"
    assert chunks[0].quality_status == "human_reviewed"
    assert chunks[0].metadata_json["production_effect"] == "none"
    assert session.flush_count == 2
    assert session.execute_count == 1


async def test_update_event_impact_link_reopens_review_and_records_learning() -> None:
    event_id = uuid4()
    link_id = uuid4()
    event_item = EventIntelligenceItem(
        id=event_id,
        source_type="news_event",
        source_id=str(uuid4()),
        title="Verified crude policy report",
        summary="Policy report has an editable impact chain.",
        event_type="policy",
        event_timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        entities=[],
        symbols=["SC"],
        regions=["middle_east_crude"],
        mechanisms=["policy"],
        evidence=["Original evidence"],
        counterevidence=[],
        confidence=0.8,
        impact_score=80,
        status="confirmed",
        requires_manual_confirmation=False,
        source_reliability=0.8,
        freshness_score=1,
        source_payload={"source_count": 2, "verification_status": "cross_verified"},
    )
    link = EventImpactLink(
        id=link_id,
        event_item_id=event_id,
        symbol="SC",
        region_id="middle_east_crude",
        mechanism="policy",
        direction="bullish",
        confidence=0.8,
        impact_score=80,
        horizon="short",
        rationale="Original rationale",
        evidence=["Original evidence"],
        counterevidence=[],
        status="confirmed",
    )
    session = FakeImpactLinkUpdateSession(event_item, [link])

    updated_event, updated_link, audit = await update_event_impact_link(
        session,  # type: ignore[arg-type]
        link_id,
        edited_by="operator",
        note="Direction should be watch until logistics evidence arrives.",
        changes={
            "direction": "watch",
            "confidence": 0.61,
            "impact_score": 61,
            "rationale": "Manual review downgraded the impact chain.",
            "counterevidence": ["Missing logistics confirmation"],
        },
    )

    assert updated_event.status == "human_review"
    assert updated_event.requires_manual_confirmation is True
    assert updated_event.confidence == 0.61
    assert updated_event.impact_score == 61
    assert updated_link.status == "human_review"
    assert updated_link.direction == "watch"
    assert audit.action == "impact_link.updated"
    assert audit.payload["before"]["direction"] == "bullish"
    assert audit.payload["after"]["direction"] == "watch"
    reviews = [row for row in session.rows if isinstance(row, ChangeReviewQueue)]
    chunks = [row for row in session.rows if isinstance(row, VectorChunk)]
    assert reviews[0].source == "event_intelligence"
    assert "manual_confirmation_required" in reviews[0].proposed_change["review_reasons"]
    assert chunks[0].chunk_type == "event_intelligence_review"
    assert chunks[0].metadata_json["action"] == "impact_link.updated"


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
        self.pending_review = ChangeReviewQueue(
            source="event_intelligence",
            target_table="event_intelligence_items",
            target_key=str(event_item.id),
            proposed_change={"event_item_id": str(event_item.id)},
            status="pending",
            reason="test review",
        )
        self.rows: list[object] = []
        self.rows.append(self.pending_review)
        self.flush_count = 0
        self.execute_count = 0

    async def get(self, model, key):
        if model is EventIntelligenceItem and key == self.event_item.id:
            return self.event_item
        return None

    async def execute(self, _):
        self.execute_count += 1

    async def scalars(self, _):
        return FakeScalars(self.pending_review if self.pending_review.status == "pending" else None)

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeReviewSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, _):
        return FakeScalars()

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeImpactLinkUpdateSession:
    def __init__(
        self,
        event_item: EventIntelligenceItem,
        links: list[EventImpactLink],
    ) -> None:
        self.event_item = event_item
        self.links = links
        self.rows: list[object] = []
        self.flush_count = 0
        self.scalar_calls = 0

    async def get(self, model, key):
        if model is EventIntelligenceItem and key == self.event_item.id:
            return self.event_item
        if model is EventImpactLink:
            return next((link for link in self.links if link.id == key), None)
        return None

    async def scalars(self, _):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return FakeScalars(rows=self.links)
        return FakeScalars()

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeScalars:
    def __init__(self, row=None, rows=None) -> None:
        self._row = row
        self._rows = rows or ([] if row is None else [row])

    def first(self):
        return self._row

    def all(self):
        return self._rows
