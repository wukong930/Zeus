from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.api.causal_web import (
    CounterContext,
    EventIntelligenceLinkContext,
    GraphNodeSeed,
    MetricContext,
    _append_edge,
    _build_edges,
    _counter_seeds_from_alert,
    _latest_market_metrics_statement,
    _layout_nodes,
    _seed_from_event_intelligence_item,
    _seed_from_event_intelligence_link,
    _unique_recent_event_intelligence,
    _unique_recent_news,
)
from app.models.alert import Alert
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack


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
