from datetime import datetime, timezone
from uuid import uuid4

from app.api.world_map import (
    WORLD_RISK_REGIONS,
    _build_region_snapshot,
    _build_world_map_tile_cells,
    _risk_level,
)
from app.models.alert import Alert
from app.models.industry_data import IndustryData
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


def test_region_snapshot_uses_runtime_weather_rows() -> None:
    now = datetime.now(timezone.utc)
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
        industry_weather=[
            IndustryData(
                symbol="NR",
                data_type="weather_precip_7d",
                value=180.0,
                unit="mm",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_temp_max_7d",
                value=34.0,
                unit="C",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_temp_min_7d",
                value=24.0,
                unit="C",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
        ],
    )

    assert region.dataQuality == "partial"
    assert region.weather.dataSource == "open_meteo+regional_baseline_seed"
    assert region.weather.rainfall7dMm == 180.0
    assert region.weather.precipitationAnomalyPct > 0
    assert region.story.evidence[0].source == "open_meteo+regional_baseline_seed"


def test_region_snapshot_uses_historical_weather_baseline_rows() -> None:
    now = datetime.now(timezone.utc)
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
        industry_weather=[
            IndustryData(
                symbol="NR",
                data_type="weather_precip_7d",
                value=180.0,
                unit="mm",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_baseline_precip_7d",
                value=90.0,
                unit="mm",
                source="nasa_power_baseline:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_baseline_temp_mean_7d",
                value=28.0,
                unit="C",
                source="nasa_power_baseline:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_precip_pctile_7d",
                value=95.0,
                unit="pctile",
                source="nasa_power_baseline:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_temp_pctile_7d",
                value=75.0,
                unit="pctile",
                source="nasa_power_baseline:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_temp_max_7d",
                value=34.0,
                unit="C",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_temp_min_7d",
                value=24.0,
                unit="C",
                source="open_meteo:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
        ],
    )

    assert region.weather.dataSource == "nasa_power_baseline+open_meteo"
    assert region.weather.precipitationAnomalyPct == 100.0
    assert region.weather.temperatureAnomalyC == 1.0
    assert region.weather.precipitationPercentile == 95.0
    assert region.weather.temperaturePercentile == 75.0
    assert region.weather.floodRisk > 0.8
    assert region.weather.confidence > 0.75


def test_region_snapshot_keeps_weather_scoped_by_location_region() -> None:
    now = datetime.now(timezone.utc)
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[4],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
        industry_weather=[
            IndustryData(
                symbol="M",
                data_type="weather_precip_7d",
                value=200.0,
                unit="mm",
                source="open_meteo:ames_iowa",
                timestamp=now,
                ingested_at=now,
            ),
        ],
    )

    assert region.id == "brazil_soy_agri"
    assert region.dataQuality == "baseline"
    assert region.weather.dataSource == "regional_baseline_seed"


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


def test_world_map_tile_contract_covers_weather_and_risk_layers() -> None:
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
    )

    cells = _build_world_map_tile_cells([region], layer="all", resolution="coarse")

    assert {cell.layer for cell in cells} == {"weather", "risk"}
    assert all(len(cell.polygon) == 4 for cell in cells)
    assert all(0 <= cell.intensity <= 1 for cell in cells)
    assert any(cell.metric in {"precipitation_anomaly_pct", "flood_risk", "drought_risk"} for cell in cells)
    assert any(cell.metric == "composite_risk" for cell in cells)


def test_world_map_tile_contract_can_filter_weather_layer() -> None:
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
    )

    cells = _build_world_map_tile_cells([region], layer="weather", resolution="medium")

    assert cells
    assert {cell.layer for cell in cells} == {"weather"}
    assert all(cell.source == "regional_baseline_seed" for cell in cells)
