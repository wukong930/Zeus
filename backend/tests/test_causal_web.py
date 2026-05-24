from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.causal_web import (
    CausalWebGraph,
    CounterContext,
    EventIntelligenceLinkContext,
    GraphNodeSeed,
    MetricContext,
    router as causal_web_router,
    _append_edge,
    _build_edges,
    _causal_scope_symbols,
    _clear_causal_web_cache,
    _counter_seeds_from_alert,
    _event_intelligence_link_statement,
    _event_intelligence_statement,
    _latest_market_metrics_statement,
    _layout_nodes,
    _linked_alerts_statement,
    _merge_pinned_event_intelligence,
    _recent_alerts_statement,
    _recent_industry_metrics_statement,
    _recent_news_statement,
    _recent_signals_statement,
    _seed_from_event_intelligence_item,
    _seed_from_event_intelligence_link,
    _unique_recent_event_intelligence,
    _unique_recent_news,
)
from app.core.database import get_db
from app.models.alert import Alert
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack
from app.services.event_intelligence import evaluate_event_intelligence_quality


def test_layout_nodes_includes_runtime_semantics() -> None:
    nodes = _layout_nodes(
        [
            GraphNodeSeed(
                id="signal-test",
                type="signal",
                label="spread_anomaly / ferrous",
                timestamp=datetime.now(timezone.utc),
                category="ferrous",
                confidence=0.72,
                tags=("spread_anomaly", "ferrous"),
                narrative="live signal",
                alert_linked=True,
            )
        ]
    )

    assert nodes[0].stage == "thesis"
    assert nodes[0].sector == "ferrous"
    assert nodes[0].freshness > 0.9
    assert nodes[0].alertLinked is True
    assert nodes[0].labelZh is not None


def test_causal_web_endpoint_uses_short_ttl_cache(monkeypatch) -> None:
    _clear_causal_web_cache()
    calls = {"count": 0}

    async def fake_db():
        yield object()

    async def fake_build_graph(
        session,
        *,
        limit: int,
        symbol_filter: str | None,
        region: str | None,
        pinned_event_item: EventIntelligenceItem | None,
    ) -> CausalWebGraph:
        calls["count"] += 1
        assert session is not None
        assert limit == 8
        assert symbol_filter == "SC"
        assert region is None
        assert pinned_event_item is None
        return CausalWebGraph(
            generated_at=datetime(2026, 5, 18, tzinfo=timezone.utc)
            + timedelta(seconds=calls["count"]),
            nodes=[],
            edges=[],
            source_counts={"signals": calls["count"]},
        )

    monkeypatch.setattr("app.api.causal_web.build_causal_web_graph", fake_build_graph)
    app = FastAPI()
    app.include_router(causal_web_router)
    app.dependency_overrides[get_db] = fake_db

    try:
        client = TestClient(app)
        first = client.get("/api/causal-web?limit=8&symbol=sc")
        second = client.get("/api/causal-web?limit=8&symbol=sc")
        refreshed = client.get("/api/causal-web?limit=8&symbol=sc&refresh=true")

        assert first.status_code == 200
        assert second.status_code == 200
        assert refreshed.status_code == 200
        assert calls["count"] == 2
        assert first.json()["generated_at"] == second.json()["generated_at"]
        assert first.json()["source_counts"]["signals"] == 1
        assert refreshed.json()["source_counts"]["signals"] == 2
    finally:
        _clear_causal_web_cache()


def test_append_edge_skips_missing_nodes_and_duplicates() -> None:
    edges = []

    _append_edge(edges, "e1", "a", "b", 0.7, "now", 0.6, "neutral", True, {"a", "b"})
    _append_edge(edges, "e2", "a", "b", 0.7, "now", 0.6, "neutral", True, {"a", "b"})
    _append_edge(edges, "e3", "a", "missing", 0.7, "now", 0.6, "neutral", True, {"a", "b"})

    assert len(edges) == 1
    assert edges[0].confidence == 0.7


def test_build_edges_links_news_metric_signal_and_alert_contexts() -> None:
    alert_id = uuid4()
    signal_id = uuid4()
    news_id = uuid4()
    metric_id = uuid4()
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=alert_id,
        title="SC 原油上涨预警",
        summary="原油偏多",
        severity="high",
        category="energy",
        type="momentum",
        status="active",
        triggered_at=now,
        confidence=0.74,
        related_assets=["SC"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    signal = SignalTrack(
        id=signal_id,
        alert_id=alert_id,
        signal_type="momentum",
        category="energy",
        confidence=0.74,
        outcome="pending",
    )
    news = NewsEvent(
        id=news_id,
        source="gdelt",
        title="Oil supply disruption",
        summary="Supply disruption lifts crude.",
        published_at=now,
        event_type="supply",
        affected_symbols=["SC"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        llm_confidence=0.7,
        verification_status="cross_verified",
        requires_manual_confirmation=False,
        dedup_hash="news-hash",
    )
    node_ids = {
        f"alert-{alert_id}",
        f"signal-{signal_id}",
        f"news-{news_id}",
        f"metric-{metric_id}",
    }

    edges = _build_edges(
        news=[news],
        metrics=[MetricContext(node_id=f"metric-{metric_id}", symbol="SC", category="energy")],
        signals=[signal],
        alerts=[alert],
        counters=[],
        node_ids=node_ids,
    )

    pairs = {(edge.source, edge.target) for edge in edges}
    assert (f"signal-{signal_id}", f"alert-{alert_id}") in pairs
    assert (f"metric-{metric_id}", f"signal-{signal_id}") in pairs
    assert (f"news-{news_id}", f"signal-{signal_id}") in pairs


def test_build_edges_links_event_intelligence_scope() -> None:
    event_item_id = uuid4()
    impact_link_id = uuid4()

    edges = _build_edges(
        news=[],
        metrics=[],
        signals=[],
        alerts=[],
        counters=[],
        node_ids={f"ei-{event_item_id}", f"ei-link-{impact_link_id}"},
        event_intelligence_links=[
            EventIntelligenceLinkContext(
                source_node_id=f"ei-{event_item_id}",
                target_node_id=f"ei-link-{impact_link_id}",
                direction="bullish",
                confidence=0.82,
                impact_score=87,
                horizon="short",
                verified=False,
            )
        ],
    )

    assert [(edge.source, edge.target, edge.direction) for edge in edges] == [
        (f"ei-{event_item_id}", f"ei-link-{impact_link_id}", "bullish")
    ]


def test_event_intelligence_seeds_use_shared_scope_ids() -> None:
    now = datetime.now(timezone.utc)
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="news_event",
        source_id="oil-1",
        title="Carrier route raises crude supply risk",
        summary="A naval route change raises crude supply risk.",
        event_type="geopolitical",
        event_timestamp=now,
        entities=["Iran", "carrier"],
        symbols=["SC"],
        regions=["middle_east_crude"],
        mechanisms=["geopolitical", "supply"],
        evidence=["route report"],
        counterevidence=[],
        confidence=0.76,
        impact_score=79,
        status="shadow_review",
        requires_manual_confirmation=False,
        source_reliability=0.7,
        freshness_score=0.9,
        source_payload={},
        created_at=now,
        updated_at=now,
    )
    impact_link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_item.id,
        symbol="SC",
        region_id="middle_east_crude",
        mechanism="geopolitical",
        direction="bullish",
        confidence=0.8,
        impact_score=82,
        horizon="short",
        rationale="Potential route tension lifts crude risk premium.",
        evidence=[],
        counterevidence=[],
        status="shadow_review",
        created_at=now,
        updated_at=now,
    )

    item_seed = _seed_from_event_intelligence_item(event_item)
    link_seed = _seed_from_event_intelligence_link(impact_link, event_item)

    assert item_seed.id == f"ei-{event_item.id}"
    assert link_seed.id == f"ei-link-{impact_link.id}"
    assert link_seed.category == "energy"
    assert link_seed.direction == "bullish"
    assert item_seed.label_zh == "地缘事件：原油"
    assert item_seed.label_en == "Carrier route raises crude supply risk"
    assert item_seed.narrative_zh is not None
    assert "证据：route report" in item_seed.narrative_zh
    assert item_seed.evidence[0].text == "route report"
    assert item_seed.evidence[0].textZh == "route report"
    assert item_seed.narrative_en is not None
    assert "Impact symbols: SC" in item_seed.narrative_en
    assert link_seed.label_zh == "SC 地缘影响假设"
    assert link_seed.narrative_zh is not None
    assert "方向：偏多" in link_seed.narrative_zh
    assert link_seed.narrative_en is not None
    assert "Direction: bullish" in link_seed.narrative_en

    item_node, link_node = _layout_nodes([item_seed, link_seed])
    assert item_node.narrativeZh == item_seed.narrative_zh
    assert item_node.tagsZh[0] == "事件智能"
    assert item_node.evidence[0].text == "route report"
    assert item_node.evidence[0].kind == "evidence"
    assert link_node.labelZh == link_seed.label_zh
    assert link_node.evidence[0].text == "route report"


def test_event_intelligence_seeds_expose_quality_gate_state() -> None:
    now = datetime.now(timezone.utc)
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="news_event",
        source_id="rubber-quality-1",
        title="Rubber rainfall disruption",
        summary="Rainfall disruption may tighten rubber supply.",
        event_type="weather",
        event_timestamp=now,
        entities=["Thailand"],
        symbols=["RU"],
        regions=["southeast_asia_rubber"],
        mechanisms=["weather", "supply"],
        evidence=["rainfall anomaly", "station percentile"],
        counterevidence=["forecast may shift"],
        confidence=0.88,
        impact_score=88,
        status="confirmed",
        requires_manual_confirmation=False,
        source_reliability=0.82,
        freshness_score=0.96,
        source_payload={},
        created_at=now,
        updated_at=now,
    )
    impact_link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_item.id,
        symbol="RU",
        region_id="southeast_asia_rubber",
        mechanism="weather",
        direction="bullish",
        confidence=0.84,
        impact_score=86,
        horizon="short",
        rationale="Rainfall reduces tapping days.",
        evidence=["rainfall anomaly"],
        counterevidence=["forecast may shift"],
        status="confirmed",
        created_at=now,
        updated_at=now,
    )
    quality = evaluate_event_intelligence_quality(event_item, [impact_link])
    link_quality = quality.link_reports[0]

    item_node, link_node = _layout_nodes(
        [
            _seed_from_event_intelligence_item(event_item, quality),
            _seed_from_event_intelligence_link(impact_link, event_item, link_quality),
        ]
    )

    assert item_node.qualityStatus == "decision_grade"
    assert item_node.qualityScore is not None and item_node.qualityScore >= 82
    assert item_node.alertLinked is True
    assert link_node.qualityStatus == "decision_grade"
    assert link_node.qualityScore is not None and link_node.qualityScore >= 60


def test_build_edges_uses_latest_signal_for_alert_link() -> None:
    alert_id = uuid4()
    old_signal_id = uuid4()
    latest_signal_id = uuid4()
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=alert_id,
        title="SC 原油上涨预警",
        summary="原油偏多",
        severity="high",
        category="energy",
        type="momentum",
        status="active",
        triggered_at=now,
        confidence=0.91,
        related_assets=["SC"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    latest_signal = SignalTrack(
        id=latest_signal_id,
        alert_id=alert_id,
        signal_type="momentum",
        category="energy",
        confidence=0.91,
        outcome="pending",
        created_at=now,
    )
    old_signal = SignalTrack(
        id=old_signal_id,
        alert_id=alert_id,
        signal_type="momentum",
        category="energy",
        confidence=0.52,
        outcome="pending",
        created_at=now - timedelta(hours=1),
    )

    edges = _build_edges(
        news=[],
        metrics=[],
        signals=[latest_signal, old_signal],
        alerts=[alert],
        counters=[],
        node_ids={
            f"signal-{latest_signal_id}",
            f"signal-{old_signal_id}",
            f"alert-{alert_id}",
        },
    )

    assert [(edge.source, edge.target, edge.confidence) for edge in edges] == [
        (f"signal-{latest_signal_id}", f"alert-{alert_id}", 0.91)
    ]


def test_build_edges_trims_by_causal_explanation_priority() -> None:
    now = datetime.now(timezone.utc)
    news = NewsEvent(
        id=uuid4(),
        source="gdelt",
        title="Oil supply disruption",
        summary="Supply disruption lifts crude.",
        published_at=now,
        event_type="supply",
        affected_symbols=["SC"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        llm_confidence=0.7,
        verification_status="cross_verified",
        requires_manual_confirmation=False,
        dedup_hash="news-hash",
    )
    metric = MetricContext(node_id=f"metric-{uuid4()}", symbol="SC", category="energy")
    alerts: list[Alert] = []
    signals: list[SignalTrack] = []
    counters: list[CounterContext] = []
    node_ids = {f"news-{news.id}", metric.node_id}

    for index in range(12):
        alert_id = uuid4()
        signal_id = uuid4()
        alerts.append(
            Alert(
                id=alert_id,
                title=f"SC 原油上涨预警 {index}",
                summary="原油偏多",
                severity="high",
                category="energy",
                type="momentum",
                status="active",
                triggered_at=now,
                confidence=0.74,
                related_assets=["SC"],
                trigger_chain=[],
                risk_items=["review inventory"],
                manual_check_items=["review source"],
            )
        )
        signals.append(
            SignalTrack(
                id=signal_id,
                alert_id=alert_id,
                signal_type="momentum",
                category="energy",
                confidence=0.74,
                outcome="pending",
                created_at=now + timedelta(seconds=index),
            )
        )
        counters.extend(
            [
                CounterContext(node_id=f"counter-{alert_id}-1", alert_id=alert_id, confidence=0.51),
                CounterContext(node_id=f"counter-{alert_id}-2", alert_id=alert_id, confidence=0.51),
            ]
        )
        node_ids.update(
            {
                f"alert-{alert_id}",
                f"signal-{signal_id}",
                f"counter-{alert_id}-1",
                f"counter-{alert_id}-2",
            }
        )

    edges = _build_edges(
        news=[news],
        metrics=[metric],
        signals=signals,
        alerts=alerts,
        counters=counters,
        node_ids=node_ids,
    )

    assert len(edges) == 24
    assert any(edge.id.startswith("edge-news-signal") for edge in edges)
    assert any(edge.id.startswith("edge-metric-signal") for edge in edges)
    assert sum(edge.id.startswith("edge-counter-alert") for edge in edges) < len(counters)


def test_counter_seeds_from_alert_create_review_nodes_and_edges() -> None:
    alert_id = uuid4()
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=alert_id,
        title="NR weather alert",
        summary="weather needs review",
        severity="medium",
        category="rubber",
        type="weather",
        status="active",
        triggered_at=now,
        confidence=0.68,
        adversarial_passed=False,
        related_assets=["NR"],
        trigger_chain=[],
        risk_items=["inventory remains high"],
        manual_check_items=["confirm rainfall source"],
    )

    counters = _counter_seeds_from_alert(alert)
    assert counters
    assert counters[0].type == "counter"

    node_ids = {f"alert-{alert_id}", counters[0].id}
    edges = _build_edges(
        news=[],
        metrics=[],
        signals=[],
        alerts=[alert],
        counters=[CounterContext(node_id=counters[0].id, alert_id=alert_id, confidence=counters[0].confidence)],
        node_ids=node_ids,
    )

    assert [(edge.source, edge.target) for edge in edges] == [(counters[0].id, f"alert-{alert_id}")]


def test_unique_recent_news_collapses_syndicated_titles() -> None:
    now = datetime.now(timezone.utc)

    def news(title: str, *, summary: str, dedup_hash: str) -> NewsEvent:
        return NewsEvent(
            id=uuid4(),
            source="gdelt",
            title=title,
            summary=summary,
            published_at=now,
            event_type="policy",
            affected_symbols=["NR", "RU"],
            direction="bullish",
            severity=3,
            time_horizon="short",
            llm_confidence=0.73,
            verification_status="single_source",
            requires_manual_confirmation=False,
            dedup_hash=dedup_hash,
        )

    first = news(
        "( Hello Africa ) China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector",
        summary="India",
        dedup_hash="news-1",
    )
    duplicate_prefix = news(
        "Feature : China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector",
        summary="Japan",
        dedup_hash="news-2",
    )
    duplicate_suffix = news(
        "China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector -- China Economic Net",
        summary="China",
        dedup_hash="news-3",
    )
    unrelated = news(
        "China zero-tariff policy expands copper trade",
        summary="Metals",
        dedup_hash="news-4",
    )

    unique = _unique_recent_news(
        [first, duplicate_prefix, duplicate_suffix, unrelated],
        limit=4,
    )

    assert [row.id for row in unique] == [first.id, unrelated.id]


def test_unique_recent_event_intelligence_collapses_syndicated_titles() -> None:
    now = datetime.now(timezone.utc)

    def event(title: str, *, summary: str) -> EventIntelligenceItem:
        return EventIntelligenceItem(
            id=uuid4(),
            source_type="news_event",
            source_id=title[:20],
            title=title,
            summary=summary,
            event_type="policy",
            event_timestamp=now,
            entities=["China", "rubber"],
            symbols=["NR", "RU"],
            regions=["southeast_asia_rubber"],
            mechanisms=["policy"],
            evidence=[],
            counterevidence=[],
            confidence=0.7,
            impact_score=70,
            status="shadow_review",
            requires_manual_confirmation=False,
            source_reliability=0.7,
            freshness_score=0.9,
            source_payload={},
            created_at=now,
            updated_at=now,
        )

    first = event(
        "( Hello Africa ) China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector",
        summary="Japan",
    )
    duplicate_prefix = event(
        "Feature : China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector",
        summary="China",
    )
    duplicate_suffix = event(
        "China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector -- China Economic Net",
        summary="United States",
    )
    unrelated = event(
        "Crude rally drives momentum in rubber stocks",
        summary="Markets",
    )

    unique = _unique_recent_event_intelligence(
        [first, duplicate_prefix, duplicate_suffix, unrelated],
        limit=4,
    )

    assert [row.id for row in unique] == [first.id, unrelated.id]


def test_merge_pinned_event_intelligence_keeps_deep_link_first() -> None:
    now = datetime.now(timezone.utc)

    def event(title: str) -> EventIntelligenceItem:
        return EventIntelligenceItem(
            id=uuid4(),
            source_type="news_event",
            source_id=title[:20],
            title=title,
            summary=title,
            event_type="policy",
            event_timestamp=now,
            entities=["China", "rubber"],
            symbols=["NR", "RU"],
            regions=["southeast_asia_rubber"],
            mechanisms=["policy"],
            evidence=[],
            counterevidence=[],
            confidence=0.7,
            impact_score=70,
            status="shadow_review",
            requires_manual_confirmation=False,
            source_reliability=0.7,
            freshness_score=0.9,
            source_payload={},
            created_at=now,
            updated_at=now,
        )

    recent = event("China zero - tariff policy opens new rubber opportunities")
    pinned = event("Pinned older rubber policy event")

    merged = _merge_pinned_event_intelligence([recent, pinned], pinned=pinned)

    assert [row.id for row in merged] == [pinned.id, recent.id]


def test_latest_market_metrics_statement_prefers_latest_row_per_symbol() -> None:
    compiled = str(
        _latest_market_metrics_statement(limit=6).compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "row_number() OVER" in compiled
    assert "PARTITION BY market_data.symbol" in compiled
    assert "market_data.ingested_at DESC" in compiled
    assert "market_data.timestamp DESC" in compiled
    assert "anon_1.rn = 1" in compiled
    assert "LIMIT 6" in compiled


def test_causal_web_scoped_statements_push_symbol_filters_to_database() -> None:
    news_sql = _compile_postgres(_recent_news_statement(limit=8, symbols=["SC"]))
    signal_sql = _compile_postgres(_recent_signals_statement(limit=8, category="energy"))
    alert_sql = _compile_postgres(_recent_alerts_statement(limit=8, symbols=["SC"]))
    industry_sql = _compile_postgres(_recent_industry_metrics_statement(limit=8, symbols=["SC"]))
    market_sql = _compile_postgres(_latest_market_metrics_statement(limit=8, symbols=["SC"]))
    event_item_sql = _compile_postgres(
        _event_intelligence_statement(limit=8, symbol="SC", region="middle_east_oil")
    )
    event_link_sql = _compile_postgres(
        _event_intelligence_link_statement(
            event_item_ids=[uuid4()],
            limit=8,
            symbol="SC",
            region="middle_east_oil",
        )
    )

    assert "news_events.affected_symbols" in news_sql
    assert "signal_track.category" in signal_sql
    assert "alerts.related_assets" in alert_sql
    assert "industry_data.symbol IN" in industry_sql
    assert "market_data.symbol IN" in market_sql
    assert "event_intelligence_items.symbols" in event_item_sql
    assert "event_impact_links.symbol =" in event_link_sql


def test_causal_web_runtime_statements_use_stable_tie_breakers() -> None:
    news_sql = _compile_postgres(_recent_news_statement(limit=8, symbols=[]))
    signal_sql = _compile_postgres(_recent_signals_statement(limit=8, category=None))
    alert_sql = _compile_postgres(_recent_alerts_statement(limit=8, symbols=[]))
    linked_alert_sql = _compile_postgres(
        _linked_alerts_statement(alert_ids=[uuid4(), uuid4()])
    )
    industry_sql = _compile_postgres(_recent_industry_metrics_statement(limit=8, symbols=[]))
    market_sql = _compile_postgres(_latest_market_metrics_statement(limit=8, symbols=[]))
    event_item_sql = _compile_postgres(
        _event_intelligence_statement(limit=8, symbol=None, region=None)
    )
    event_link_sql = _compile_postgres(
        _event_intelligence_link_statement(
            event_item_ids=[uuid4()],
            limit=8,
            symbol=None,
            region=None,
        )
    )

    assert "ORDER BY news_events.published_at DESC, news_events.id DESC" in news_sql
    assert "ORDER BY signal_track.created_at DESC, signal_track.id DESC" in signal_sql
    assert "ORDER BY alerts.triggered_at DESC, alerts.id DESC" in alert_sql
    assert "ORDER BY alerts.triggered_at DESC, alerts.id DESC" in linked_alert_sql
    assert "ORDER BY industry_data.ingested_at DESC, industry_data.id DESC" in industry_sql
    assert "market_data.id DESC" in market_sql
    assert (
        "ORDER BY event_intelligence_items.event_timestamp DESC, "
        "event_intelligence_items.created_at DESC, event_intelligence_items.id DESC"
    ) in event_item_sql
    assert (
        "ORDER BY event_impact_links.impact_score DESC, "
        "event_impact_links.confidence DESC, event_impact_links.id DESC"
    ) in event_link_sql


def test_causal_scope_symbols_merges_query_and_pinned_event_symbols() -> None:
    now = datetime.now(timezone.utc)
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="news_event",
        source_id="scope-1",
        title="Scope event",
        summary="Scope event",
        event_type="weather",
        event_timestamp=now,
        entities=[],
        symbols=["SC", "RU"],
        regions=[],
        mechanisms=[],
        evidence=[],
        counterevidence=[],
        confidence=0.8,
        impact_score=80,
        status="shadow_review",
        requires_manual_confirmation=False,
        source_reliability=0.8,
        freshness_score=0.9,
        source_payload={},
        created_at=now,
        updated_at=now,
    )

    assert _causal_scope_symbols("sc", event_item) == ["SC", "RU"]


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
