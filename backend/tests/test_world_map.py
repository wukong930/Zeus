from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.world_map import (
    WORLD_RISK_REGIONS,
    WorldMapFilterScope,
    WorldMapTileViewport,
    _alert_symbols,
    _build_region_snapshot,
    _build_world_map_tile_cells,
    _clear_world_map_caches,
    _event_intelligence_display_key,
    _filter_tile_cells_for_viewport,
    _matched_event_intelligence_items,
    _risk_level,
    _symbols_intersect,
    _unique_recent_event_intelligence,
    _world_map_alerts_statement,
    _world_map_event_items_statement,
    _world_map_event_links_statement,
    _world_map_news_statement,
    _world_map_positions_statement,
    _world_map_should_load_source,
    _world_map_signals_statement,
    _world_map_weather_statement,
    _weather_row_key,
)
from app.core.database import get_db
from app.main import create_app
from app.models.alert import Alert
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.industry_data import IndustryData
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack


def _baseline_region():
    return _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
    )


def test_risk_level_buckets_are_ordered() -> None:
    assert _risk_level(20) == "low"
    assert _risk_level(40) == "watch"
    assert _risk_level(58) == "elevated"
    assert _risk_level(75) == "high"
    assert _risk_level(90) == "critical"


def test_world_map_scoped_statements_push_filters_to_database() -> None:
    filters = WorldMapFilterScope(symbol="SC", mechanism="energy_cost", source="all")
    alert_sql = _compile_postgres(_world_map_alerts_statement(limit=20, filters=filters))
    news_sql = _compile_postgres(_world_map_news_statement(limit=20, filters=filters))
    signal_sql = _compile_postgres(_world_map_signals_statement(limit=20, alert_ids=[uuid4()]))
    position_sql = _compile_postgres(_world_map_positions_statement(limit=20))
    event_item_sql = _compile_postgres(_world_map_event_items_statement(limit=20, filters=filters))
    event_link_sql = _compile_postgres(
        _world_map_event_links_statement(event_item_ids=[uuid4()], limit=20, filters=filters)
    )

    assert "alerts.related_assets" in alert_sql
    assert "news_events.affected_symbols" in news_sql
    assert "signal_track.alert_id IN" in signal_sql
    assert "positions.status IN" in position_sql
    assert "event_intelligence_items.symbols" in event_item_sql
    assert "event_impact_links.symbol =" in event_link_sql
    assert "event_impact_links.mechanism =" in event_link_sql


def test_world_map_runtime_statements_use_stable_tie_breakers() -> None:
    alert_sql = _compile_postgres(_world_map_alerts_statement(limit=20, filters=None))
    news_sql = _compile_postgres(_world_map_news_statement(limit=20, filters=None))
    signal_sql = _compile_postgres(_world_map_signals_statement(limit=20, alert_ids=[uuid4()]))
    position_sql = _compile_postgres(_world_map_positions_statement(limit=20))
    weather_sql = _compile_postgres(_world_map_weather_statement(limit=20))
    event_item_sql = _compile_postgres(_world_map_event_items_statement(limit=20, filters=None))
    event_link_sql = _compile_postgres(
        _world_map_event_links_statement(event_item_ids=[uuid4()], limit=20, filters=None)
    )

    assert "ORDER BY alerts.triggered_at DESC, alerts.id DESC" in alert_sql
    assert "ORDER BY news_events.published_at DESC, news_events.id DESC" in news_sql
    assert "ORDER BY signal_track.created_at DESC, signal_track.id DESC" in signal_sql
    assert "ORDER BY positions.opened_at DESC, positions.id DESC" in position_sql
    assert (
        "ORDER BY industry_data.timestamp DESC, "
        "industry_data.ingested_at DESC, industry_data.id DESC"
    ) in weather_sql
    assert (
        "ORDER BY event_intelligence_items.event_timestamp DESC, "
        "event_intelligence_items.created_at DESC, event_intelligence_items.id DESC"
    ) in event_item_sql
    assert (
        "ORDER BY event_impact_links.impact_score DESC, "
        "event_impact_links.confidence DESC, event_impact_links.id DESC"
    ) in event_link_sql


def test_world_map_source_filter_skips_unneeded_runtime_sources() -> None:
    weather_filters = WorldMapFilterScope(source="weather")
    signal_filters = WorldMapFilterScope(source="signal")

    assert _world_map_should_load_source(weather_filters, "alert") is False
    assert _world_map_should_load_source(weather_filters, "event_intelligence") is False
    assert _world_map_should_load_source(signal_filters, "signal") is True
    assert _world_map_should_load_source(signal_filters, "alert") is False
    assert _world_map_should_load_source(None, "position") is True


def test_world_map_weather_row_key_uses_id_tie_breaker() -> None:
    observed_at = datetime(2026, 5, 3, tzinfo=timezone.utc)
    older_id = UUID("00000000-0000-0000-0000-000000000001")
    newer_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    older_row = IndustryData(
        id=older_id,
        symbol="RU",
        data_type="weather_precipitation_anomaly_pct",
        value=12,
        unit="pct",
        source="open_meteo:thailand_south",
        timestamp=observed_at,
        ingested_at=observed_at,
    )
    newer_row = IndustryData(
        id=newer_id,
        symbol="RU",
        data_type="weather_precipitation_anomaly_pct",
        value=18,
        unit="pct",
        source="open_meteo:thailand_south",
        timestamp=observed_at,
        ingested_at=observed_at,
    )

    assert _weather_row_key(newer_row) > _weather_row_key(older_row)


def test_world_map_snapshot_endpoint_uses_short_ttl_cache(monkeypatch) -> None:
    _clear_world_map_caches()
    calls: dict[str, int] = {"load": 0}
    region = _baseline_region()

    async def fake_db():
        yield object()

    async def fake_load_regions(_session, *, limit, filters):
        calls["load"] += 1
        assert limit == 20
        assert filters.symbol is None
        return [region]

    monkeypatch.setattr("app.api.world_map._load_world_map_regions", fake_load_regions)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    first = client.get("/api/world-map?limit=20")
    second = client.get("/api/world-map?limit=20")
    refreshed = client.get("/api/world-map?limit=20&refresh=true")

    assert first.status_code == 200
    assert second.status_code == 200
    assert refreshed.status_code == 200
    assert calls["load"] == 2
    assert first.json()["generatedAt"] == second.json()["generatedAt"]
    assert first.json()["regions"][0]["id"] == WORLD_RISK_REGIONS[0].id
    _clear_world_map_caches()


def test_world_map_tiles_endpoint_uses_short_ttl_cache(monkeypatch) -> None:
    _clear_world_map_caches()
    calls: dict[str, int] = {"load": 0}
    region = _baseline_region()

    async def fake_db():
        yield object()

    async def fake_load_regions(_session, *, limit, filters):
        calls["load"] += 1
        assert limit == 20
        assert filters.symbol == "RU"
        return [region]

    monkeypatch.setattr("app.api.world_map._load_world_map_regions", fake_load_regions)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)
    path = (
        "/api/world-map/tiles?limit=20&symbol=RU&resolution=coarse"
        "&min_lat=-20&max_lat=20&min_lon=80&max_lon=140"
    )

    first = client.get(path)
    second = client.get(path)
    refreshed = client.get(f"{path}&refresh=true")

    assert first.status_code == 200
    assert second.status_code == 200
    assert refreshed.status_code == 200
    assert calls["load"] == 2
    assert first.json()["generatedAt"] == second.json()["generatedAt"]
    assert first.json()["resolution"] == "coarse"
    _clear_world_map_caches()


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
    assert region.riskMomentum.direction == "rising"
    assert region.riskMomentum.delta > 0
    assert region.riskMomentum.intensity > 0
    assert region.riskMomentum.changedAt == now
    assert region.evidenceHealth.evidenceCount >= len(region.story.evidence)
    assert region.evidenceHealth.counterEvidenceCount == len(region.story.counterEvidence)
    assert region.evidenceHealth.runtimeSources >= 4
    assert region.evidenceHealth.freshRuntimeSources >= 3
    assert region.evidenceHealth.densityScore > 50
    assert 0 <= region.evidenceHealth.sourceReliability <= 100
    assert 0 <= region.evidenceHealth.freshnessScore <= 100


def test_region_snapshot_uses_event_intelligence_scope() -> None:
    now = datetime.now(timezone.utc)
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="news_event",
        source_id="rubber-policy-1",
        title="China zero-tariff policy opens rubber trade",
        summary="Tariff change may redirect natural rubber trade into China.",
        event_type="policy",
        event_timestamp=now,
        entities=["China", "rubber"],
        symbols=["RU", "NR"],
        regions=["southeast_asia_rubber"],
        mechanisms=["policy", "supply"],
        evidence=["policy headline"],
        counterevidence=["execution details pending"],
        confidence=0.81,
        impact_score=83,
        status="shadow_review",
        requires_manual_confirmation=False,
        source_reliability=0.72,
        freshness_score=0.94,
        source_payload={},
        created_at=now,
        updated_at=now,
    )
    impact_link = EventImpactLink(
        id=uuid4(),
        event_item_id=event_item.id,
        symbol="RU",
        region_id="southeast_asia_rubber",
        mechanism="policy",
        direction="bullish",
        confidence=0.84,
        impact_score=86,
        horizon="short",
        rationale="Tariff policy can pull rubber demand forward.",
        evidence=["policy headline"],
        counterevidence=["details pending"],
        status="shadow_review",
        created_at=now,
        updated_at=now,
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
        event_items=[event_item],
        event_links=[impact_link],
    )

    assert region.runtime.eventIntelligence == 1
    assert region.eventQuality.status == "shadow_ready"
    assert region.eventQuality.passed == 1
    assert region.eventQuality.score >= 70
    assert region.dataQuality == "runtime"
    assert region.causalScope.hasDirectLinks is True
    assert f"event_intelligence:{event_item.id}" in region.causalScope.eventIds
    assert any(row.kind == "event_intelligence" for row in region.story.evidence)
    assert any(alert.source == "event_intelligence" for alert in region.adaptiveAlerts)
    assert region.riskScore > WORLD_RISK_REGIONS[0].base_risk
    assert "event_intelligence" in region.sourceKinds
    assert "policy_shift" in region.mechanisms


def test_region_snapshot_source_filter_scopes_runtime_evidence() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="RU 降水扰动预警",
        summary="暴雨影响割胶",
        severity="high",
        category="rubber",
        type="weather",
        status="active",
        triggered_at=now,
        confidence=0.82,
        related_assets=["RU"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="news_event",
        source_id="rubber-policy-filter",
        title="Rubber policy update",
        summary="Policy update may support rubber flows.",
        event_type="policy",
        event_timestamp=now,
        entities=["rubber"],
        symbols=["RU"],
        regions=["southeast_asia_rubber"],
        mechanisms=["policy"],
        evidence=["policy headline"],
        counterevidence=[],
        confidence=0.78,
        impact_score=80,
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
        symbol="RU",
        region_id="southeast_asia_rubber",
        mechanism="policy",
        direction="bullish",
        confidence=0.8,
        impact_score=82,
        horizon="short",
        rationale="Policy supports flows.",
        evidence=["policy headline"],
        counterevidence=[],
        status="shadow_review",
        created_at=now,
        updated_at=now,
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[alert],
        news=[],
        signals=[],
        positions=[],
        event_items=[event_item],
        event_links=[impact_link],
        filters=WorldMapFilterScope(source="event_intelligence", mechanism="policy_shift"),
    )

    assert region.runtime.alerts == 0
    assert region.runtime.eventIntelligence == 1
    assert region.sourceKinds == ["event_intelligence"]
    assert region.mechanisms == ["policy_shift"]
    assert all(row.kind == "event_intelligence" for row in region.story.evidence)


def test_region_snapshot_keeps_low_quality_event_intelligence_for_review_without_risk_boost() -> None:
    now = datetime.now(timezone.utc)
    event_item = EventIntelligenceItem(
        id=uuid4(),
        source_type="social",
        source_id="rumor-1",
        title="Unverified rubber rumor",
        summary="Single source rumor lacks evidence.",
        event_type="policy",
        event_timestamp=now,
        entities=[],
        symbols=["RU"],
        regions=["southeast_asia_rubber"],
        mechanisms=["policy"],
        evidence=[],
        counterevidence=[],
        confidence=0.42,
        impact_score=70,
        status="human_review",
        requires_manual_confirmation=True,
        source_reliability=0.3,
        freshness_score=0.9,
        source_payload={},
        created_at=now,
        updated_at=now,
    )

    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
        event_items=[event_item],
        event_links=[],
    )

    assert region.runtime.eventIntelligence == 1
    assert region.eventQuality.status == "blocked"
    assert region.eventQuality.blocked == 1
    assert region.eventQuality.passed == 0
    assert not any(row.kind == "event_intelligence" for row in region.story.evidence)
    assert region.riskMomentum.direction == "easing"
    assert region.riskMomentum.delta < 0
    assert region.riskMomentum.driverZh == "质量门阻断"


def test_world_map_event_intelligence_dedupe_keeps_one_display_event() -> None:
    now = datetime.now(timezone.utc)

    def event(title: str) -> EventIntelligenceItem:
        return EventIntelligenceItem(
            id=uuid4(),
            source_type="news_event",
            source_id=title[:20],
            title=title,
            summary="Rubber policy update",
            event_type="policy",
            event_timestamp=now,
            entities=["China", "rubber"],
            symbols=["RU", "NR"],
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

    unique = _unique_recent_event_intelligence(
        [
            event("( Hello Africa ) China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector"),
            event("Feature : China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector"),
            event("China zero - tariff policy opens new opportunities for Cote dIvoire rubber sector -- China Economic Net"),
        ],
        limit=10,
    )

    assert len(unique) == 1


def test_world_map_runtime_symbol_matching_normalizes_contract_values() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="Rubber rainfall warning",
        summary="Natural rubber supply risk",
        severity="high",
        category="rubber",
        type="weather",
        status="active",
        triggered_at=now,
        confidence=0.82,
        related_assets=[" ru2509 ", "", "NR"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    assert _alert_symbols(alert) == {"RU", "NR"}
    assert _symbols_intersect({" ru2509 ", ""}, {"RU"}) is True


def test_world_map_event_intelligence_symbol_scope_normalizes_contract_values() -> None:
    now = datetime.now(timezone.utc)

    def event(symbols: list[str]) -> EventIntelligenceItem:
        return EventIntelligenceItem(
            id=uuid4(),
            source_type="news_event",
            source_id="rubber-contract-scope",
            title="China zero - tariff policy opens rubber trade",
            summary="Tariff change may redirect natural rubber trade into China.",
            event_type="policy",
            event_timestamp=now,
            entities=["China", "rubber"],
            symbols=symbols,
            regions=[],
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

    dirty = event([" ru2509 ", "", "NR"])
    clean = event(["RU", "NR"])

    assert _matched_event_intelligence_items(WORLD_RISK_REGIONS[0], [dirty]) == [dirty]
    assert _event_intelligence_display_key(dirty) == _event_intelligence_display_key(clean)


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
    assert region.riskMomentum.direction == "steady"
    assert region.riskMomentum.delta == 0
    assert region.riskMomentum.intensity == 0
    assert region.evidenceHealth.runtimeSources == 1
    assert region.evidenceHealth.freshRuntimeSources == 0
    assert region.evidenceHealth.freshnessScore < 40


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


def test_region_snapshot_surfaces_current_weather_rows_without_7d_precip() -> None:
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
                data_type="weather_temp_current_c",
                value=32.6,
                unit="C",
                source="accuweather:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_precip_1h",
                value=6.1,
                unit="mm",
                source="accuweather:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_humidity_pct",
                value=88.0,
                unit="pct",
                source="accuweather:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
            IndustryData(
                symbol="NR",
                data_type="weather_wind_kph",
                value=18.4,
                unit="km/h",
                source="accuweather:hat_yai",
                timestamp=now,
                ingested_at=now,
            ),
        ],
    )

    assert region.dataQuality == "partial"
    assert region.weather.dataSource == "accuweather+regional_baseline_seed"
    assert region.weather.currentTemperatureC == 32.6
    assert region.weather.precipitation1hMm == 6.1
    assert region.weather.humidityPct == 88.0
    assert region.weather.windKph == 18.4


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


def test_world_map_tile_viewport_filters_cells() -> None:
    region = _build_region_snapshot(
        WORLD_RISK_REGIONS[0],
        alerts=[],
        news=[],
        signals=[],
        positions=[],
    )
    cells = _build_world_map_tile_cells([region], layer="all", resolution="medium")
    selected = cells[0]
    viewport = WorldMapTileViewport(
        min_lat=max(selected.center.lat - 2, -85),
        max_lat=min(selected.center.lat + 2, 85),
        min_lon=max(selected.center.lon - 2, -180),
        max_lon=min(selected.center.lon + 2, 180),
    )

    filtered = _filter_tile_cells_for_viewport(cells, viewport)

    assert filtered
    assert len(filtered) < len(cells)
    assert selected.id in {cell.id for cell in filtered}


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
