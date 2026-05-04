from datetime import datetime, timezone
from uuid import uuid4

from app.api.causal_web import (
    GraphNodeSeed,
    MetricContext,
    _append_edge,
    _build_edges,
    _layout_nodes,
)
from app.models.alert import Alert
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
        node_ids=node_ids,
    )

    pairs = {(edge.source, edge.target) for edge in edges}
    assert (f"signal-{signal_id}", f"alert-{alert_id}") in pairs
    assert (f"metric-{metric_id}", f"signal-{signal_id}") in pairs
    assert (f"news-{news_id}", f"signal-{signal_id}") in pairs
