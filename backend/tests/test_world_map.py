from datetime import datetime, timezone
from uuid import uuid4

from app.api.world_map import (
    WORLD_RISK_REGIONS,
    _build_region_snapshot,
    _risk_level,
)
from app.models.alert import Alert
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack


def test_risk_level_buckets_are_ordered() -> None:
    assert _risk_level(20) == "low"
    assert _risk_level(40) == "watch"
    assert _risk_level(58) == "elevated"
    assert _risk_level(75) == "high"
    assert _risk_level(90) == "critical"


def test_region_snapshot_links_runtime_sources() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="RU 东南亚降水扰动预警",
        summary="RU 与 NR 供应扰动",
        severity="high",
        category="rubber",
        type="weather",
        status="active",
        triggered_at=now,
        confidence=0.82,
        related_assets=["RU", "NR"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    news = NewsEvent(
        id=uuid4(),
        source="gdelt",
        title="Thailand rubber rainfall disruption",
        summary="Heavy rainfall delays tapping.",
        published_at=now,
        event_type="weather",
        affected_symbols=["RU"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        llm_confidence=0.72,
        verification_status="cross_verified",
        requires_manual_confirmation=False,
        dedup_hash="rubber-rainfall",
    )
    signal = SignalTrack(
        id=uuid4(),
        alert_id=alert.id,
        signal_type="inventory_shock",
        category="rubber",
        confidence=0.77,
        outcome="pending",
        created_at=now,
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[alert],
        news=[news],
        signals=[signal],
        positions=[],
    )

    assert region.runtime.alerts == 1
    assert region.runtime.newsEvents == 1
    assert region.runtime.signals == 1
    assert region.runtime.highSeverityAlerts == 1
    assert region.dataQuality == "runtime"
    assert region.causalScope.hasDirectLinks is True
    assert any(event_id.startswith("alert:") for event_id in region.causalScope.eventIds)
    assert region.riskScore > WORLD_RISK_REGIONS[0].base_risk
    assert region.story.triggerZh
    assert region.story.chain
    assert any(step.stage == "production" for step in region.story.chain)
    assert region.adaptiveAlerts
    assert region.adaptiveAlerts[0].source in {"alert", "news"}


def test_region_snapshot_keeps_baseline_label_without_runtime_links() -> None:
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[2],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
    )

    assert region.dataQuality == "baseline"
    assert region.causalScope.hasDirectLinks is False
    assert region.weather.dataSource == "regional_baseline_seed"
    assert region.story.evidence[0].kind == "weather"


def test_region_snapshot_does_not_link_category_only_signals() -> None:
    now = datetime.now(timezone.utc)
    signal = SignalTrack(
        id=uuid4(),
        alert_id=None,
        signal_type="momentum",
        category="ferrous",
        confidence=0.91,
        outcome="pending",
        created_at=now,
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[2],
        alerts=[],
        news=[],
        signals=[signal],
        positions=[],
    )

    assert region.runtime.signals == 0
    assert region.causalScope.hasDirectLinks is False


def test_same_flood_factor_adapts_to_commodity_lens() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="I 澳洲港口暴雨影响运输",
        summary="暴雨和港口运输扰动影响铁矿发运",
        severity="medium",
        category="ferrous",
        type="weather",
        status="active",
        triggered_at=now,
        confidence=0.68,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[2],
        alerts=[alert],
        news=[],
        signals=[],
        positions=[],
    )

    labels = [step.labelZh for step in region.story.chain]
    assert any("港口" in label or "运输" in label for label in labels)
    assert region.story.triggerZh
    assert region.adaptiveAlerts[0].mechanismZh
