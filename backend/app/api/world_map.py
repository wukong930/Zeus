from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.news_events import NewsEvent
from app.models.position import Position
from app.models.signal import SignalTrack

router = APIRouter(prefix="/api/world-map", tags=["world-map"])

RiskLevel = Literal["low", "watch", "elevated", "high", "critical"]
DataQuality = Literal["runtime", "partial", "baseline"]
LayerStatus = Literal["ready", "baseline", "planned"]


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class WorldMapWeather(BaseModel):
    precipitationAnomalyPct: float
    rainfall7dMm: float
    temperatureAnomalyC: float
    floodRisk: float = Field(ge=0, le=1)
    droughtRisk: float = Field(ge=0, le=1)
    dataSource: str
    confidence: float = Field(ge=0, le=1)


class WorldMapRuntime(BaseModel):
    alerts: int
    highSeverityAlerts: int
    newsEvents: int
    signals: int
    positions: int
    latestEventAt: datetime | None = None


class WorldMapDriver(BaseModel):
    labelZh: str
    labelEn: str
    weight: float = Field(ge=0, le=1)


class WorldMapCausalScope(BaseModel):
    regionId: str
    symbols: list[str]
    eventIds: list[str]
    causalWebUrl: str
    hasDirectLinks: bool


class WorldMapRegion(BaseModel):
    id: str
    nameZh: str
    nameEn: str
    commodityZh: str
    commodityEn: str
    symbols: list[str]
    center: GeoPoint
    polygon: list[GeoPoint]
    riskScore: int = Field(ge=0, le=100)
    riskLevel: RiskLevel
    drivers: list[WorldMapDriver]
    weather: WorldMapWeather
    runtime: WorldMapRuntime
    causalScope: WorldMapCausalScope
    narrativeZh: str
    narrativeEn: str
    dataQuality: DataQuality


class WorldMapLayer(BaseModel):
    id: str
    labelZh: str
    labelEn: str
    status: LayerStatus
    enabled: bool


class WorldMapSummary(BaseModel):
    regions: int
    elevatedRegions: int
    maxRiskScore: int
    runtimeLinkedRegions: int


class WorldMapSnapshot(BaseModel):
    generatedAt: datetime
    summary: WorldMapSummary
    layers: list[WorldMapLayer]
    regions: list[WorldMapRegion]


@dataclass(frozen=True)
class WeatherBaseline:
    precipitation_anomaly_pct: float
    rainfall_7d_mm: float
    temperature_anomaly_c: float
    flood_risk: float
    drought_risk: float
    confidence: float


@dataclass(frozen=True)
class RegionDefinition:
    id: str
    name_zh: str
    name_en: str
    commodity_zh: str
    commodity_en: str
    symbols: tuple[str, ...]
    center: tuple[float, float]
    polygon: tuple[tuple[float, float], ...]
    baseline_weather: WeatherBaseline
    base_risk: int
    narrative_zh: str
    narrative_en: str


WORLD_RISK_REGIONS: tuple[RegionDefinition, ...] = (
    RegionDefinition(
        id="southeast_asia_rubber",
        name_zh="东南亚橡胶产区",
        name_en="Southeast Asia Rubber Belt",
        commodity_zh="橡胶",
        commodity_en="Rubber",
        symbols=("RU", "NR", "BR"),
        center=(12.5, 101.0),
        polygon=((24.0, 96.0), (22.0, 108.0), (9.0, 112.0), (-8.0, 106.0), (-5.0, 96.0), (10.0, 94.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=18.0,
            rainfall_7d_mm=96.0,
            temperature_anomaly_c=0.7,
            flood_risk=0.62,
            drought_risk=0.18,
            confidence=0.58,
        ),
        base_risk=34,
        narrative_zh="橡胶产区重点跟踪降水、割胶节奏与 NR/RU 传导。",
        narrative_en="Rubber belt watches rainfall, tapping pace, and NR/RU transmission.",
    ),
    RegionDefinition(
        id="middle_east_crude",
        name_zh="中东原油链路",
        name_en="Middle East Crude Corridor",
        commodity_zh="原油",
        commodity_en="Crude Oil",
        symbols=("SC",),
        center=(27.5, 47.0),
        polygon=((34.0, 35.0), (33.0, 57.0), (22.0, 59.0), (15.0, 48.0), (20.0, 36.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=-8.0,
            rainfall_7d_mm=12.0,
            temperature_anomaly_c=1.2,
            flood_risk=0.12,
            drought_risk=0.46,
            confidence=0.54,
        ),
        base_risk=38,
        narrative_zh="原油链路重点跟踪供应扰动、航运节点与 SC 价格传导。",
        narrative_en="Crude corridor tracks supply disruption, shipping nodes, and SC transmission.",
    ),
    RegionDefinition(
        id="australia_iron_ore",
        name_zh="澳洲铁矿供应区",
        name_en="Australia Iron Ore Supply",
        commodity_zh="黑色",
        commodity_en="Ferrous",
        symbols=("I", "RB", "HC"),
        center=(-23.5, 121.5),
        polygon=((-13.0, 113.0), (-14.0, 132.0), (-30.0, 136.0), (-36.0, 119.0), (-25.0, 112.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=6.0,
            rainfall_7d_mm=34.0,
            temperature_anomaly_c=0.4,
            flood_risk=0.28,
            drought_risk=0.22,
            confidence=0.55,
        ),
        base_risk=28,
        narrative_zh="黑色链路重点跟踪铁矿发运、港口天气与成材利润。",
        narrative_en="Ferrous chain tracks iron ore shipments, port weather, and steel margins.",
    ),
    RegionDefinition(
        id="north_china_ferrous",
        name_zh="华北黑色需求区",
        name_en="North China Ferrous Demand",
        commodity_zh="黑色",
        commodity_en="Ferrous",
        symbols=("RB", "HC", "J", "JM", "I"),
        center=(38.5, 116.5),
        polygon=((42.0, 109.0), (42.0, 123.0), (34.0, 124.0), (33.0, 112.0), (37.0, 108.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=-5.0,
            rainfall_7d_mm=18.0,
            temperature_anomaly_c=-0.2,
            flood_risk=0.16,
            drought_risk=0.32,
            confidence=0.52,
        ),
        base_risk=32,
        narrative_zh="需求区重点跟踪施工季节、环保扰动和炉料成本传导。",
        narrative_en="Demand hub tracks construction season, policy disruption, and feedstock costs.",
    ),
    RegionDefinition(
        id="brazil_soy_agri",
        name_zh="巴西农产天气带",
        name_en="Brazil Agriculture Weather Belt",
        commodity_zh="农产",
        commodity_en="Agriculture",
        symbols=("M", "Y", "P"),
        center=(-15.5, -52.0),
        polygon=((-5.0, -62.0), (-7.0, -43.0), (-24.0, -42.0), (-28.0, -56.0), (-16.0, -66.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=-14.0,
            rainfall_7d_mm=42.0,
            temperature_anomaly_c=1.0,
            flood_risk=0.20,
            drought_risk=0.58,
            confidence=0.50,
        ),
        base_risk=36,
        narrative_zh="农产天气带重点跟踪降水距平、物流和油粕传导。",
        narrative_en="Agriculture belt tracks precipitation anomaly, logistics, and oilmeal transmission.",
    ),
    RegionDefinition(
        id="us_grains_energy",
        name_zh="北美农能联动区",
        name_en="North America Agri-Energy Link",
        commodity_zh="农能",
        commodity_en="Agri-Energy",
        symbols=("M", "Y", "SC"),
        center=(39.0, -96.0),
        polygon=((49.0, -124.0), (48.0, -72.0), (29.0, -77.0), (25.0, -103.0), (35.0, -124.0)),
        baseline_weather=WeatherBaseline(
            precipitation_anomaly_pct=9.0,
            rainfall_7d_mm=55.0,
            temperature_anomaly_c=0.6,
            flood_risk=0.36,
            drought_risk=0.30,
            confidence=0.48,
        ),
        base_risk=26,
        narrative_zh="北美区域重点跟踪天气、能源价格与农产品成本联动。",
        narrative_en="North America tracks weather, energy prices, and agriculture cost linkage.",
    ),
)


@router.get("", response_model=WorldMapSnapshot)
async def get_world_map(
    limit: int = Query(default=200, ge=20, le=500),
    session: AsyncSession = Depends(get_db),
) -> WorldMapSnapshot:
    alerts = list(
        (
            await session.scalars(
                select(Alert)
                .where(Alert.status != "suppressed")
                .order_by(Alert.triggered_at.desc())
                .limit(limit)
            )
        ).all()
    )
    news = list(
        (
            await session.scalars(
                select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(limit)
            )
        ).all()
    )
    signals = list(
        (
            await session.scalars(
                select(SignalTrack).order_by(SignalTrack.created_at.desc()).limit(limit)
            )
        ).all()
    )
    positions = list(
        (
            await session.scalars(
                select(Position)
                .where(Position.status.in_(["open", "position_aware"]))
                .order_by(Position.opened_at.desc())
                .limit(limit)
            )
        ).all()
    )
    regions = [
        _build_region_snapshot(
            definition,
            alerts=alerts,
            news=news,
            signals=signals,
            positions=positions,
        )
        for definition in WORLD_RISK_REGIONS
    ]
    regions.sort(key=lambda region: region.riskScore, reverse=True)
    return WorldMapSnapshot(
        generatedAt=datetime.now(timezone.utc),
        summary=WorldMapSummary(
            regions=len(regions),
            elevatedRegions=sum(region.riskScore >= 55 for region in regions),
            maxRiskScore=max((region.riskScore for region in regions), default=0),
            runtimeLinkedRegions=sum(region.causalScope.hasDirectLinks for region in regions),
        ),
        layers=_world_map_layers(),
        regions=regions,
    )


def _build_region_snapshot(
    definition: RegionDefinition,
    *,
    alerts: list[Alert],
    news: list[NewsEvent],
    signals: list[SignalTrack],
    positions: list[Position],
) -> WorldMapRegion:
    region_symbols = set(definition.symbols)
    matched_alerts = [row for row in alerts if _symbols_intersect(_alert_symbols(row), region_symbols)]
    matched_news = [row for row in news if _symbols_intersect(set(row.affected_symbols or []), region_symbols)]
    matched_alert_ids = {row.id for row in matched_alerts}
    matched_signals = [
        row for row in signals if row.alert_id is not None and row.alert_id in matched_alert_ids
    ]
    matched_positions = [row for row in positions if _symbols_intersect(_position_symbols(row), region_symbols)]
    latest_event_at = _latest_event_at(matched_alerts, matched_news, matched_signals)
    high_severity_alerts = sum(row.severity in {"critical", "high"} for row in matched_alerts)
    avg_signal_confidence = (
        sum(row.confidence for row in matched_signals) / len(matched_signals)
        if matched_signals
        else 0.0
    )
    weather_risk = max(
        abs(definition.baseline_weather.precipitation_anomaly_pct) / 40,
        definition.baseline_weather.flood_risk,
        definition.baseline_weather.drought_risk,
    )
    risk_score = _clamp_int(
        definition.base_risk
        + round(weather_risk * 18)
        + len(matched_alerts) * 8
        + high_severity_alerts * 10
        + len(matched_news) * 4
        + round(avg_signal_confidence * 12)
        + len(matched_positions) * 6,
        0,
        100,
    )
    event_ids = [
        *[f"alert:{row.id}" for row in matched_alerts[:6]],
        *[f"news:{row.id}" for row in matched_news[:6]],
    ]
    runtime = WorldMapRuntime(
        alerts=len(matched_alerts),
        highSeverityAlerts=high_severity_alerts,
        newsEvents=len(matched_news),
        signals=len(matched_signals),
        positions=len(matched_positions),
        latestEventAt=latest_event_at,
    )
    return WorldMapRegion(
        id=definition.id,
        nameZh=definition.name_zh,
        nameEn=definition.name_en,
        commodityZh=definition.commodity_zh,
        commodityEn=definition.commodity_en,
        symbols=list(definition.symbols),
        center=GeoPoint(lat=definition.center[0], lon=definition.center[1]),
        polygon=[GeoPoint(lat=lat, lon=lon) for lat, lon in definition.polygon],
        riskScore=risk_score,
        riskLevel=_risk_level(risk_score),
        drivers=_region_drivers(definition, runtime, weather_risk),
        weather=WorldMapWeather(
            precipitationAnomalyPct=definition.baseline_weather.precipitation_anomaly_pct,
            rainfall7dMm=definition.baseline_weather.rainfall_7d_mm,
            temperatureAnomalyC=definition.baseline_weather.temperature_anomaly_c,
            floodRisk=definition.baseline_weather.flood_risk,
            droughtRisk=definition.baseline_weather.drought_risk,
            dataSource="regional_baseline_seed",
            confidence=definition.baseline_weather.confidence,
        ),
        runtime=runtime,
        causalScope=WorldMapCausalScope(
            regionId=definition.id,
            symbols=list(definition.symbols),
            eventIds=event_ids,
            causalWebUrl=f"/causal-web?symbol={definition.symbols[0]}&region={definition.id}",
            hasDirectLinks=bool(event_ids or matched_signals or matched_positions),
        ),
        narrativeZh=definition.narrative_zh,
        narrativeEn=definition.narrative_en,
        dataQuality=_data_quality(runtime),
    )


def _world_map_layers() -> list[WorldMapLayer]:
    return [
        WorldMapLayer(id="weather", labelZh="天气异常", labelEn="Weather Anomaly", status="baseline", enabled=True),
        WorldMapLayer(id="alerts", labelZh="预警热力", labelEn="Alert Heat", status="ready", enabled=True),
        WorldMapLayer(id="causal", labelZh="因果联动", labelEn="Causal Linkage", status="ready", enabled=True),
        WorldMapLayer(id="positions", labelZh="持仓暴露", labelEn="Position Exposure", status="ready", enabled=True),
        WorldMapLayer(id="globe", labelZh="3D 地球", labelEn="3D Globe", status="planned", enabled=False),
    ]


def _risk_level(score: int) -> RiskLevel:
    if score >= 85:
        return "critical"
    if score >= 72:
        return "high"
    if score >= 55:
        return "elevated"
    if score >= 38:
        return "watch"
    return "low"


def _region_drivers(
    definition: RegionDefinition,
    runtime: WorldMapRuntime,
    weather_risk: float,
) -> list[WorldMapDriver]:
    drivers = [
        WorldMapDriver(labelZh="天气距平", labelEn="Weather anomaly", weight=min(weather_risk, 1.0)),
    ]
    if runtime.highSeverityAlerts:
        drivers.append(
            WorldMapDriver(labelZh="高等级预警", labelEn="High severity alerts", weight=min(runtime.highSeverityAlerts / 4, 1.0))
        )
    if runtime.newsEvents:
        drivers.append(
            WorldMapDriver(labelZh="新闻事件", labelEn="News events", weight=min(runtime.newsEvents / 8, 1.0))
        )
    if runtime.signals:
        drivers.append(
            WorldMapDriver(labelZh="活跃信号", labelEn="Active signals", weight=min(runtime.signals / 10, 1.0))
        )
    if runtime.positions:
        drivers.append(
            WorldMapDriver(labelZh="持仓暴露", labelEn="Position exposure", weight=min(runtime.positions / 5, 1.0))
        )
    if len(drivers) == 1:
        drivers.append(
            WorldMapDriver(labelZh=f"{definition.commodity_zh}基线", labelEn=f"{definition.commodity_en} baseline", weight=0.35)
        )
    return drivers[:4]


def _data_quality(runtime: WorldMapRuntime) -> DataQuality:
    if runtime.alerts or runtime.newsEvents or runtime.signals or runtime.positions:
        return "runtime"
    return "baseline"


def _alert_symbols(alert: Alert) -> set[str]:
    values = {str(value).upper() for value in (alert.related_assets or [])}
    values.update(_extract_symbol_tokens(alert.title))
    values.update(_extract_symbol_tokens(alert.summary))
    return values


def _position_symbols(position: Position) -> set[str]:
    values: set[str] = set()
    for leg in position.legs or []:
        if isinstance(leg, dict):
            for key in ("symbol", "contract", "asset"):
                value = leg.get(key)
                if isinstance(value, str) and value:
                    values.add(_root_symbol(value))
    values.update(_extract_symbol_tokens(position.strategy_name or ""))
    return values


def _extract_symbol_tokens(text: str) -> set[str]:
    upper = text.upper()
    tokens: set[str] = set()
    for definition in WORLD_RISK_REGIONS:
        for symbol in definition.symbols:
            if symbol in upper:
                tokens.add(symbol)
    return tokens


def _symbols_intersect(values: set[str], region_symbols: set[str]) -> bool:
    return bool({_root_symbol(value) for value in values} & region_symbols)


def _root_symbol(value: str) -> str:
    upper = value.upper().strip()
    for index, char in enumerate(upper):
        if char.isdigit():
            return upper[:index] or upper
    return upper


def _latest_event_at(
    alerts: list[Alert],
    news: list[NewsEvent],
    signals: list[SignalTrack],
) -> datetime | None:
    timestamps: list[datetime] = []
    timestamps.extend(row.triggered_at for row in alerts if row.triggered_at)
    timestamps.extend(row.published_at for row in news if row.published_at)
    timestamps.extend(row.created_at for row in signals if row.created_at)
    if not timestamps:
        return None
    return max(timestamps)


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
