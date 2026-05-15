from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.industry_data import IndustryData
from app.models.news_events import NewsEvent
from app.models.position import Position
from app.models.signal import SignalTrack
from app.schemas.event_intelligence import EventImpactLinkQualityRead, EventIntelligenceQualityRead
from app.services.data_sources.open_meteo import DEFAULT_WEATHER_LOCATIONS
from app.services.event_intelligence import evaluate_event_intelligence_quality

router = APIRouter(prefix="/api/world-map", tags=["world-map"])

RiskLevel = Literal["low", "watch", "elevated", "high", "critical"]
DataQuality = Literal["runtime", "partial", "baseline"]
LayerStatus = Literal["ready", "baseline", "planned"]
RiskMomentumDirection = Literal["rising", "easing", "steady"]
TileLayer = Literal["weather", "risk"]
TileLayerFilter = Literal["all", "weather", "risk"]
TileResolution = Literal["coarse", "medium"]
TileMetric = Literal[
    "precipitation_anomaly_pct",
    "flood_risk",
    "drought_risk",
    "composite_risk",
]
RiskFactor = Literal[
    "rainfall_surplus",
    "drought_heat",
    "el_nino",
    "supply_disruption",
    "logistics_disruption",
    "inventory_pressure",
    "policy_shift",
    "demand_shift",
    "energy_cost",
]
StoryStage = Literal[
    "climate",
    "weather_regime",
    "production",
    "logistics",
    "supply",
    "demand",
    "inventory",
    "policy",
    "cost",
    "market",
]
EvidenceKind = Literal["weather", "alert", "news", "signal", "position", "event_intelligence", "baseline"]
WorldMapSourceFilter = Literal["all", "weather", "alert", "news", "signal", "position", "event_intelligence"]
EventQualityStatus = Literal["blocked", "review", "shadow_ready", "decision_grade"]


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class WorldMapWeather(BaseModel):
    precipitationAnomalyPct: float
    rainfall7dMm: float
    temperatureAnomalyC: float
    floodRisk: float = Field(ge=0, le=1)
    droughtRisk: float = Field(ge=0, le=1)
    precipitationPercentile: float | None = Field(default=None, ge=0, le=100)
    temperaturePercentile: float | None = Field(default=None, ge=0, le=100)
    currentTemperatureC: float | None = None
    precipitation1hMm: float | None = None
    humidityPct: float | None = Field(default=None, ge=0, le=100)
    windKph: float | None = Field(default=None, ge=0)
    dataSource: str
    confidence: float = Field(ge=0, le=1)


class WorldMapRuntime(BaseModel):
    alerts: int
    highSeverityAlerts: int
    newsEvents: int
    signals: int
    positions: int
    eventIntelligence: int
    latestEventAt: datetime | None = None


class WorldMapEventQuality(BaseModel):
    status: EventQualityStatus | None = None
    score: int = Field(ge=0, le=100)
    total: int
    blocked: int
    review: int
    shadowReady: int
    decisionGrade: int
    passed: int


class WorldMapEvidenceHealth(BaseModel):
    evidenceCount: int
    counterEvidenceCount: int
    runtimeSources: int
    freshRuntimeSources: int
    sourceReliability: int = Field(ge=0, le=100)
    freshnessScore: int = Field(ge=0, le=100)
    densityScore: int = Field(ge=0, le=100)


class WorldMapRiskMomentum(BaseModel):
    direction: RiskMomentumDirection
    delta: int = Field(ge=-100, le=100)
    intensity: float = Field(ge=0, le=1)
    driverZh: str
    driverEn: str
    reasonZh: str
    reasonEn: str
    changedAt: datetime | None = None


class WorldMapDriver(BaseModel):
    labelZh: str
    labelEn: str
    weight: float = Field(ge=0, le=1)


class WorldMapEvidenceItem(BaseModel):
    kind: EvidenceKind
    titleZh: str
    titleEn: str
    source: str
    weight: float = Field(ge=0, le=1)


class WorldMapStoryStep(BaseModel):
    stage: StoryStage
    labelZh: str
    labelEn: str
    confidence: float = Field(ge=0, le=1)
    evidenceKind: EvidenceKind


class WorldMapRiskStory(BaseModel):
    headlineZh: str
    headlineEn: str
    triggerZh: str
    triggerEn: str
    chain: list[WorldMapStoryStep]
    evidence: list[WorldMapEvidenceItem]
    counterEvidence: list[WorldMapEvidenceItem]


class WorldMapAdaptiveAlert(BaseModel):
    id: str
    titleZh: str
    titleEn: str
    severity: RiskLevel
    triggerZh: str
    triggerEn: str
    mechanismZh: str
    mechanismEn: str
    confidence: float = Field(ge=0, le=1)
    source: EvidenceKind


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
    riskMomentum: WorldMapRiskMomentum
    drivers: list[WorldMapDriver]
    weather: WorldMapWeather
    runtime: WorldMapRuntime
    story: WorldMapRiskStory
    adaptiveAlerts: list[WorldMapAdaptiveAlert]
    causalScope: WorldMapCausalScope
    mechanisms: list[RiskFactor] = Field(default_factory=list)
    sourceKinds: list[EvidenceKind] = Field(default_factory=list)
    eventQuality: WorldMapEventQuality
    evidenceHealth: WorldMapEvidenceHealth
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


class WorldMapFilterOption(BaseModel):
    id: str
    labelZh: str
    labelEn: str


class WorldMapFilterOptions(BaseModel):
    symbols: list[str]
    mechanisms: list[WorldMapFilterOption]
    sources: list[WorldMapFilterOption]


class WorldMapSnapshot(BaseModel):
    generatedAt: datetime
    summary: WorldMapSummary
    filters: WorldMapFilterOptions
    layers: list[WorldMapLayer]
    regions: list[WorldMapRegion]


class WorldMapTileCell(BaseModel):
    id: str
    layer: TileLayer
    regionId: str
    center: GeoPoint
    polygon: list[GeoPoint]
    metric: TileMetric
    value: float
    intensity: float = Field(ge=0, le=1)
    riskLevel: RiskLevel
    dataQuality: DataQuality
    source: str


class WorldMapTileSummary(BaseModel):
    weatherCells: int
    riskCells: int
    maxIntensity: float = Field(ge=0, le=1)
    dataSources: list[str]


class WorldMapTileSnapshot(BaseModel):
    generatedAt: datetime
    resolution: TileResolution
    layer: TileLayerFilter
    summary: WorldMapTileSummary
    cells: list[WorldMapTileCell]


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


@dataclass(frozen=True)
class FactorSignal:
    factor: RiskFactor
    weight: float
    evidence_kind: EvidenceKind
    label_zh: str
    label_en: str
    source: str


@dataclass(frozen=True)
class CommodityLens:
    label_zh: str
    label_en: str
    default_factor: RiskFactor
    factor_steps: dict[RiskFactor, tuple[tuple[StoryStage, str, str], ...]]
    counter_templates: dict[RiskFactor, tuple[str, str]]


@dataclass(frozen=True)
class WorldMapFilterScope:
    symbol: str | None = None
    mechanism: RiskFactor | None = None
    source: WorldMapSourceFilter = "all"


@dataclass(frozen=True)
class WorldMapTileViewport:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


GENERIC_COUNTER_TEMPLATES: dict[RiskFactor, tuple[str, str]] = {
    "rainfall_surplus": ("库存或进口补充可能缓冲天气扰动。", "Inventory or imports may buffer the weather shock."),
    "drought_heat": ("需求偏弱可能削弱天气风险对价格的传导。", "Weak demand may soften weather transmission into prices."),
    "el_nino": ("ENSO 概率变化不等于单一区域产量已经确认下降。", "ENSO probability does not confirm local output loss yet."),
    "supply_disruption": ("替代供应和库存释放可能降低供应扰动强度。", "Alternative supply and stock release may dilute disruption."),
    "logistics_disruption": ("物流扰动若持续时间短，价格影响可能快速回吐。", "Short logistics disruptions may fade quickly."),
    "inventory_pressure": ("库存信号需和需求、利润、基差共同确认。", "Inventory signals need demand, margin, and basis confirmation."),
    "policy_shift": ("政策口径可能调整，需等待执行细则。", "Policy language may shift; implementation details matter."),
    "demand_shift": ("需求变化可能已被盘面提前交易。", "Demand changes may already be priced in."),
    "energy_cost": ("能源成本传导可能被产业利润压缩吸收。", "Energy cost transmission may be absorbed by margin compression."),
}

WORLD_MAP_MECHANISM_ORDER: tuple[RiskFactor, ...] = (
    "rainfall_surplus",
    "drought_heat",
    "el_nino",
    "supply_disruption",
    "logistics_disruption",
    "inventory_pressure",
    "policy_shift",
    "demand_shift",
    "energy_cost",
)

WORLD_MAP_SOURCE_LABELS: dict[WorldMapSourceFilter, tuple[str, str]] = {
    "all": ("全部来源", "All Sources"),
    "weather": ("天气", "Weather"),
    "alert": ("预警", "Alerts"),
    "news": ("新闻", "News"),
    "signal": ("信号", "Signals"),
    "position": ("持仓", "Positions"),
    "event_intelligence": ("事件智能", "Event Intelligence"),
}


COMMODITY_LENSES: dict[str, CommodityLens] = {
    "rubber": CommodityLens(
        label_zh="橡胶",
        label_en="Rubber",
        default_factor="rainfall_surplus",
        factor_steps={
            "rainfall_surplus": (
                ("climate", "降水异常或洪涝抬升割胶难度", "Rainfall anomaly or flood risk disrupts tapping"),
                ("production", "割胶天数下降，原料胶水上量不稳", "Tapping days fall and field latex flow becomes unstable"),
                ("supply", "天然橡胶短期供应弹性下降", "Natural rubber short-term supply elasticity tightens"),
                ("market", "NR/RU 价格和价差获得支撑", "NR/RU prices and spreads gain support"),
            ),
            "drought_heat": (
                ("climate", "高温少雨压制胶树状态", "Heat and dryness pressure rubber tree conditions"),
                ("production", "割胶节奏和单产预期下修", "Tapping pace and yield expectations are revised lower"),
                ("supply", "产区供应预期偏紧", "Origin supply expectations tighten"),
                ("market", "橡胶价格波动率上升", "Rubber price volatility rises"),
            ),
            "el_nino": (
                ("weather_regime", "厄尔尼诺概率上升改变降水分布", "Rising El Nino odds reshape rainfall distribution"),
                ("production", "主产区割胶窗口和病虫害风险重估", "Tapping windows and disease risk are repriced"),
                ("supply", "远月供应弹性被市场重新定价", "Deferred supply elasticity is repriced"),
                ("market", "NR/RU 跨期和内外价差敏感度上升", "NR/RU calendar and import spreads become more sensitive"),
            ),
            "logistics_disruption": (
                ("logistics", "港口、道路或船期延迟影响到港", "Port, road, or vessel delays affect arrivals"),
                ("supply", "可交割库存补充节奏变慢", "Deliverable inventory replenishment slows"),
                ("market", "近月合约和现货升贴水更敏感", "Nearby contracts and spot basis become more sensitive"),
            ),
            "inventory_pressure": (
                ("inventory", "库存变化改变供应缓冲", "Inventory changes alter supply buffer"),
                ("supply", "可流通货源松紧重新评估", "Tradable supply tightness is reassessed"),
                ("market", "NR/RU 价差进入再定价窗口", "NR/RU spread enters repricing window"),
            ),
        },
        counter_templates=GENERIC_COUNTER_TEMPLATES,
    ),
    "energy": CommodityLens(
        label_zh="原油",
        label_en="Crude Oil",
        default_factor="supply_disruption",
        factor_steps={
            "supply_disruption": (
                ("supply", "产油国供应或出口节点出现扰动", "Producer supply or export nodes are disrupted"),
                ("logistics", "航运、保险或装船节奏影响到港成本", "Shipping, insurance, or loading pace affects landing cost"),
                ("inventory", "区域库存和可交割资源缓冲被消耗", "Regional inventory and deliverable buffers are consumed"),
                ("market", "SC 价格和月差风险溢价上升", "SC price and calendar spread risk premium rises"),
            ),
            "logistics_disruption": (
                ("logistics", "航运瓶颈改变原油到港节奏", "Shipping bottlenecks alter crude arrival cadence"),
                ("supply", "进口可得性和炼厂采购节奏受扰", "Import availability and refinery procurement are disrupted"),
                ("market", "SC 价格对外盘和运费变化更敏感", "SC becomes more sensitive to overseas prices and freight"),
            ),
            "policy_shift": (
                ("policy", "制裁、配额或政策口径改变贸易路径", "Sanctions, quotas, or policy shifts reroute trade"),
                ("supply", "可采购资源和结算成本重估", "Accessible barrels and settlement costs are repriced"),
                ("market", "原油风险溢价上升", "Crude risk premium rises"),
            ),
            "energy_cost": (
                ("cost", "能源链成本上移", "Energy chain costs move higher"),
                ("demand", "炼厂利润和开工弹性被压缩", "Refining margins and run-rate elasticity compress"),
                ("market", "SC 价格进入成本驱动再定价", "SC enters cost-driven repricing"),
            ),
        },
        counter_templates=GENERIC_COUNTER_TEMPLATES,
    ),
    "ferrous": CommodityLens(
        label_zh="黑色",
        label_en="Ferrous",
        default_factor="logistics_disruption",
        factor_steps={
            "rainfall_surplus": (
                ("climate", "强降水影响矿山、港口或施工节奏", "Heavy rainfall affects mines, ports, or construction"),
                ("logistics", "发运、到港和钢材运输效率下降", "Shipments, arrivals, and steel logistics slow"),
                ("supply", "炉料或成材阶段性错配", "Feedstock or finished steel faces temporary mismatch"),
                ("market", "I/RB/HC/JM/J 链路重新定价", "I/RB/HC/JM/J chain is repriced"),
            ),
            "logistics_disruption": (
                ("logistics", "港口、铁路或汽运瓶颈影响库存流向", "Port, rail, or trucking bottlenecks alter inventory flow"),
                ("inventory", "港口库存和厂内库存结构变化", "Port and mill inventory structure changes"),
                ("cost", "炉料成本与成材利润重新平衡", "Feedstock costs and steel margins rebalance"),
                ("market", "黑色链路价差波动加大", "Ferrous chain spreads become more volatile"),
            ),
            "policy_shift": (
                ("policy", "环保、限产或地产政策改变需求/供给假设", "Policy alters demand or supply assumptions"),
                ("supply", "钢厂开工和炉料采购节奏调整", "Mill runs and feedstock buying adjust"),
                ("market", "成材利润和炉料价差重估", "Steel margin and feedstock spreads are repriced"),
            ),
            "demand_shift": (
                ("demand", "施工和制造需求预期变化", "Construction and manufacturing demand expectations shift"),
                ("inventory", "表需和库存去化速度改变", "Apparent demand and destocking pace change"),
                ("market", "RB/HC 价格弹性变化", "RB/HC price elasticity changes"),
            ),
        },
        counter_templates=GENERIC_COUNTER_TEMPLATES,
    ),
    "agri": CommodityLens(
        label_zh="农产",
        label_en="Agriculture",
        default_factor="drought_heat",
        factor_steps={
            "drought_heat": (
                ("climate", "高温干旱影响作物生长窗口", "Heat and drought hit crop growth windows"),
                ("production", "单产和收割进度预期下修", "Yield and harvest progress expectations are revised lower"),
                ("supply", "出口供应和压榨原料预期收紧", "Export supply and crush input expectations tighten"),
                ("market", "油粕价格和跨品种价差敏感度上升", "Oilmeal prices and cross-product spreads become more sensitive"),
            ),
            "rainfall_surplus": (
                ("climate", "过量降水或洪涝影响播种/收割", "Excess rainfall or flooding affects planting or harvest"),
                ("logistics", "内陆运输和港口装运节奏放慢", "Inland logistics and port loading slow"),
                ("supply", "可出口货源节奏后移", "Exportable supply cadence shifts later"),
                ("market", "M/Y/P 价格预期重新分配", "M/Y/P price expectations are redistributed"),
            ),
            "logistics_disruption": (
                ("logistics", "运输瓶颈影响到港和压榨节奏", "Logistics bottlenecks affect arrivals and crush pace"),
                ("inventory", "港口库存和油厂库存缓冲变化", "Port and crusher inventory buffers change"),
                ("market", "油粕基差和月差波动扩大", "Oilmeal basis and calendar spreads widen"),
            ),
            "demand_shift": (
                ("demand", "饲料、食用或生柴需求预期改变", "Feed, edible, or biofuel demand expectations shift"),
                ("inventory", "库存去化节奏重新评估", "Destocking pace is reassessed"),
                ("market", "M/Y/P 相对强弱切换", "M/Y/P relative strength rotates"),
            ),
        },
        counter_templates=GENERIC_COUNTER_TEMPLATES,
    ),
    "agri_energy": CommodityLens(
        label_zh="农能",
        label_en="Agri-Energy",
        default_factor="energy_cost",
        factor_steps={
            "energy_cost": (
                ("cost", "能源价格改变种植、运输和生柴成本", "Energy prices alter farming, logistics, and biofuel costs"),
                ("demand", "生柴和压榨利润重新计算", "Biofuel and crush margins are recalculated"),
                ("market", "农产和能源之间的替代关系增强", "Agriculture-energy substitution strengthens"),
            ),
            "rainfall_surplus": (
                ("climate", "过量降水影响作物和运输窗口", "Excess rainfall affects crop and transport windows"),
                ("logistics", "内陆运输、港口装运和能源物流同步承压", "Inland, port, and energy logistics are pressured"),
                ("supply", "农产到港与能源链补库节奏错配", "Agriculture arrivals and energy restocking become mismatched"),
                ("market", "农产和能源联动价差波动上升", "Agri-energy linked spreads become more volatile"),
            ),
        },
        counter_templates=GENERIC_COUNTER_TEMPLATES,
    ),
}

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

WORLD_MAP_WEATHER_DATA_TYPES = frozenset(
    {
        "weather_precip_7d",
        "weather_temp_max_7d",
        "weather_temp_min_7d",
        "weather_baseline_precip_7d",
        "weather_baseline_temp_mean_7d",
        "weather_precip_pctile_7d",
        "weather_temp_pctile_7d",
        "weather_precip_1h",
        "weather_temp_current_c",
        "weather_humidity_pct",
        "weather_wind_kph",
    }
)
BASELINE_WEATHER_SOURCE = "regional_baseline_seed"
WEATHER_REGION_BY_LOCATION_KEY = {
    location.key: location.region_id
    for location in DEFAULT_WEATHER_LOCATIONS
    if location.region_id is not None
}


@router.get("", response_model=WorldMapSnapshot)
async def get_world_map(
    limit: int = Query(default=200, ge=20, le=500),
    symbol: str | None = Query(default=None, min_length=1, max_length=20),
    mechanism: RiskFactor | None = Query(default=None),
    source: WorldMapSourceFilter = Query(default="all"),
    session: AsyncSession = Depends(get_db),
) -> WorldMapSnapshot:
    filters = WorldMapFilterScope(
        symbol=_normalize_filter_symbol(symbol),
        mechanism=mechanism,
        source=source,
    )
    regions = await _load_world_map_regions(session, limit=limit, filters=filters)
    return WorldMapSnapshot(
        generatedAt=datetime.now(timezone.utc),
        summary=WorldMapSummary(
            regions=len(regions),
            elevatedRegions=sum(region.riskScore >= 55 for region in regions),
            maxRiskScore=max((region.riskScore for region in regions), default=0),
            runtimeLinkedRegions=sum(region.causalScope.hasDirectLinks for region in regions),
        ),
        filters=_world_map_filter_options(),
        layers=_world_map_layers(
            weather_runtime=any(region.weather.dataSource != BASELINE_WEATHER_SOURCE for region in regions)
        ),
        regions=regions,
    )


@router.get("/tiles", response_model=WorldMapTileSnapshot)
async def get_world_map_tiles(
    layer: TileLayerFilter = Query(default="all"),
    resolution: TileResolution = Query(default="coarse"),
    limit: int = Query(default=200, ge=20, le=500),
    symbol: str | None = Query(default=None, min_length=1, max_length=20),
    mechanism: RiskFactor | None = Query(default=None),
    source: WorldMapSourceFilter = Query(default="all"),
    min_lat: float | None = Query(default=None, ge=-85, le=85),
    max_lat: float | None = Query(default=None, ge=-85, le=85),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    session: AsyncSession = Depends(get_db),
) -> WorldMapTileSnapshot:
    filters = WorldMapFilterScope(
        symbol=_normalize_filter_symbol(symbol),
        mechanism=mechanism,
        source=source,
    )
    viewport = _world_map_tile_viewport(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )
    regions = await _load_world_map_regions(session, limit=limit, filters=filters)
    cells = _filter_tile_cells_for_viewport(
        _build_world_map_tile_cells(regions, layer=layer, resolution=resolution),
        viewport,
    )
    data_sources = sorted({cell.source for cell in cells})
    return WorldMapTileSnapshot(
        generatedAt=datetime.now(timezone.utc),
        resolution=resolution,
        layer=layer,
        summary=WorldMapTileSummary(
            weatherCells=sum(cell.layer == "weather" for cell in cells),
            riskCells=sum(cell.layer == "risk" for cell in cells),
            maxIntensity=max((cell.intensity for cell in cells), default=0.0),
            dataSources=data_sources,
        ),
        cells=cells,
    )


async def _load_world_map_regions(
    session: AsyncSession,
    *,
    limit: int,
    filters: WorldMapFilterScope | None = None,
) -> list[WorldMapRegion]:
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
    weather_rows = list(
        (
            await session.scalars(
                select(IndustryData)
                .where(IndustryData.data_type.in_(WORLD_MAP_WEATHER_DATA_TYPES))
                .order_by(IndustryData.timestamp.desc(), IndustryData.ingested_at.desc())
                .limit(min(max(limit * 8, 200), 4000))
            )
        ).all()
    )
    event_items = _unique_recent_event_intelligence(
        list(
            (
                await session.scalars(
                    select(EventIntelligenceItem)
                    .where(EventIntelligenceItem.status != "rejected")
                    .order_by(EventIntelligenceItem.event_timestamp.desc(), EventIntelligenceItem.created_at.desc())
                    .limit(min(max(limit * 4, 100), 1000))
                )
            ).all()
        ),
        limit=limit,
    )
    event_links = (
        list(
            (
                await session.scalars(
                    select(EventImpactLink)
                    .where(
                        EventImpactLink.event_item_id.in_([row.id for row in event_items]),
                        EventImpactLink.status != "rejected",
                    )
                    .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
                    .limit(min(max(limit * 2, 100), 1000))
                )
            ).all()
        )
        if event_items
        else []
    )
    definitions = [
        definition
        for definition in WORLD_RISK_REGIONS
        if filters is None or filters.symbol is None or filters.symbol in definition.symbols
    ]
    regions = [
        _build_region_snapshot(
            definition,
            alerts=alerts,
            news=news,
            signals=signals,
            positions=positions,
            event_items=event_items,
            event_links=event_links,
            industry_weather=weather_rows,
            filters=filters,
        )
        for definition in definitions
    ]
    regions = [region for region in regions if _region_matches_filter_scope(region, filters)]
    regions.sort(key=lambda region: region.riskScore, reverse=True)
    return regions


def _world_map_filter_options() -> WorldMapFilterOptions:
    symbols = sorted({symbol for definition in WORLD_RISK_REGIONS for symbol in definition.symbols})
    return WorldMapFilterOptions(
        symbols=symbols,
        mechanisms=[
            WorldMapFilterOption(id=factor, labelZh=_factor_label_zh(factor), labelEn=_factor_label_en(factor))
            for factor in WORLD_MAP_MECHANISM_ORDER
        ],
        sources=[
            WorldMapFilterOption(id=source, labelZh=labels[0], labelEn=labels[1])
            for source, labels in WORLD_MAP_SOURCE_LABELS.items()
        ],
    )


def _normalize_filter_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _region_matches_filter_scope(region: WorldMapRegion, filters: WorldMapFilterScope | None) -> bool:
    if filters is None:
        return True
    if filters.source != "all" and filters.source not in region.sourceKinds:
        return False
    if filters.mechanism is not None and filters.mechanism not in region.mechanisms:
        return False
    return True


def _build_region_snapshot(
    definition: RegionDefinition,
    *,
    alerts: list[Alert],
    news: list[NewsEvent],
    signals: list[SignalTrack],
    positions: list[Position],
    event_items: list[EventIntelligenceItem] | None = None,
    event_links: list[EventImpactLink] | None = None,
    industry_weather: list[IndustryData] | None = None,
    filters: WorldMapFilterScope | None = None,
) -> WorldMapRegion:
    region_symbols = set(definition.symbols)
    matched_alerts = [row for row in alerts if _symbols_intersect(_alert_symbols(row), region_symbols)]
    matched_news = [row for row in news if _symbols_intersect(set(row.affected_symbols or []), region_symbols)]
    matched_event_items = _matched_event_intelligence_items(definition, event_items or [])
    matched_event_links = _matched_event_intelligence_links(definition, matched_event_items, event_links or [])
    matched_alert_ids = {row.id for row in matched_alerts}
    matched_signals = [
        row for row in signals if row.alert_id is not None and row.alert_id in matched_alert_ids
    ]
    matched_positions = [row for row in positions if _symbols_intersect(_position_symbols(row), region_symbols)]
    matched_alerts, matched_news, matched_signals, matched_positions, matched_event_items, matched_event_links = (
        _apply_source_filter(
            filters,
            matched_alerts=matched_alerts,
            matched_news=matched_news,
            matched_signals=matched_signals,
            matched_positions=matched_positions,
            matched_event_items=matched_event_items,
            matched_event_links=matched_event_links,
        )
    )
    matched_alerts, matched_news, matched_signals, matched_positions, matched_event_items, matched_event_links = (
        _apply_mechanism_filter(
            filters,
            matched_alerts=matched_alerts,
            matched_news=matched_news,
            matched_signals=matched_signals,
            matched_positions=matched_positions,
            matched_event_items=matched_event_items,
            matched_event_links=matched_event_links,
        )
    )
    event_quality_reports = _event_intelligence_quality_reports(matched_event_items, matched_event_links)
    event_quality = _world_map_event_quality(event_quality_reports)
    link_quality_by_id = _event_intelligence_link_quality_map(event_quality_reports)
    quality_weight = _event_quality_weight(event_quality.status)
    latest_event_at = _latest_event_at(matched_alerts, matched_news, matched_signals, matched_event_items)
    high_severity_alerts = sum(row.severity in {"critical", "high"} for row in matched_alerts)
    weather = _region_weather(definition, industry_weather or [])
    weather_risk = max(
        abs(weather.precipitationAnomalyPct) / 40,
        weather.floodRisk,
        weather.droughtRisk,
    )
    lens = _commodity_lens(definition)
    factor_signals = _factor_signals(
        definition,
        lens=lens,
        matched_alerts=matched_alerts,
        matched_news=matched_news,
        matched_signals=matched_signals,
        matched_positions=matched_positions,
        matched_event_links=matched_event_links,
        event_link_quality_by_id=link_quality_by_id,
        weather=weather,
        weather_risk=weather_risk,
    )
    factor_signals = _filter_factor_signals(factor_signals, filters)
    mechanisms = _factor_mechanisms(factor_signals)
    source_kinds = _source_kinds(
        factor_signals,
        matched_alerts=matched_alerts,
        matched_news=matched_news,
        matched_signals=matched_signals,
        matched_positions=matched_positions,
        matched_event_items=matched_event_items,
    )
    avg_signal_confidence = (
        sum(row.confidence for row in matched_signals) / len(matched_signals)
        if matched_signals
        else 0.0
    )
    event_intelligence_confidence = (
        _mean(
            [
                *[
                    row.confidence * _event_quality_weight(event_quality_reports[row.id].status)
                    for row in matched_event_items
                    if row.id in event_quality_reports
                ],
                *[
                    row.confidence * _link_quality_weight(link_quality_by_id.get(row.id))
                    for row in matched_event_links
                ],
            ]
        )
        or 0.0
    )
    risk_score = _clamp_int(
        definition.base_risk
        + round(weather_risk * 18)
        + round(sum(signal.weight for signal in factor_signals[:3]) * 8)
        + len(matched_alerts) * 8
        + high_severity_alerts * 10
        + len(matched_news) * 4
        + round(avg_signal_confidence * 12)
        + len(matched_positions) * 6
        + round(event_quality.passed * 5 + event_quality.review * 1.5)
        + round(event_intelligence_confidence * 10 * quality_weight),
        0,
        100,
    )
    event_ids = [
        *[f"event_intelligence:{row.id}" for row in matched_event_items[:6]],
        *[f"alert:{row.id}" for row in matched_alerts[:6]],
        *[f"news:{row.id}" for row in matched_news[:6]],
    ]
    runtime = WorldMapRuntime(
        alerts=len(matched_alerts),
        highSeverityAlerts=high_severity_alerts,
        newsEvents=len(matched_news),
        signals=len(matched_signals),
        positions=len(matched_positions),
        eventIntelligence=len(matched_event_items),
        latestEventAt=latest_event_at,
    )
    story = _risk_story(definition, lens, factor_signals, runtime)
    adaptive_alerts = _adaptive_alerts(
        definition,
        story=story,
        factor_signals=factor_signals,
        risk_score=risk_score,
        runtime=runtime,
    )
    evidence_health = _world_map_evidence_health(
        story=story,
        adaptive_alerts=adaptive_alerts,
        runtime=runtime,
        weather=weather,
        event_quality=event_quality,
    )
    risk_momentum = _world_map_risk_momentum(
        definition=definition,
        runtime=runtime,
        weather=weather,
        event_quality=event_quality,
        evidence_health=evidence_health,
        factor_signals=factor_signals,
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
        riskMomentum=risk_momentum,
        drivers=_region_drivers(definition, runtime, factor_signals),
        weather=weather,
        runtime=runtime,
        story=story,
        adaptiveAlerts=adaptive_alerts,
        causalScope=WorldMapCausalScope(
            regionId=definition.id,
            symbols=list(definition.symbols),
            eventIds=event_ids,
            causalWebUrl=f"/causal-web?symbol={definition.symbols[0]}&region={definition.id}",
            hasDirectLinks=bool(event_ids or matched_signals or matched_positions or matched_event_links),
        ),
        mechanisms=mechanisms,
        sourceKinds=source_kinds,
        eventQuality=event_quality,
        evidenceHealth=evidence_health,
        narrativeZh=definition.narrative_zh,
        narrativeEn=definition.narrative_en,
        dataQuality=_data_quality(runtime, weather),
    )


def _apply_source_filter(
    filters: WorldMapFilterScope | None,
    *,
    matched_alerts: list[Alert],
    matched_news: list[NewsEvent],
    matched_signals: list[SignalTrack],
    matched_positions: list[Position],
    matched_event_items: list[EventIntelligenceItem],
    matched_event_links: list[EventImpactLink],
) -> tuple[
    list[Alert],
    list[NewsEvent],
    list[SignalTrack],
    list[Position],
    list[EventIntelligenceItem],
    list[EventImpactLink],
]:
    if filters is None or filters.source == "all":
        return matched_alerts, matched_news, matched_signals, matched_positions, matched_event_items, matched_event_links
    if filters.source == "weather":
        return [], [], [], [], [], []
    return (
        matched_alerts if filters.source == "alert" else [],
        matched_news if filters.source == "news" else [],
        matched_signals if filters.source == "signal" else [],
        matched_positions if filters.source == "position" else [],
        matched_event_items if filters.source == "event_intelligence" else [],
        matched_event_links if filters.source == "event_intelligence" else [],
    )


def _apply_mechanism_filter(
    filters: WorldMapFilterScope | None,
    *,
    matched_alerts: list[Alert],
    matched_news: list[NewsEvent],
    matched_signals: list[SignalTrack],
    matched_positions: list[Position],
    matched_event_items: list[EventIntelligenceItem],
    matched_event_links: list[EventImpactLink],
) -> tuple[
    list[Alert],
    list[NewsEvent],
    list[SignalTrack],
    list[Position],
    list[EventIntelligenceItem],
    list[EventImpactLink],
]:
    if filters is None or filters.mechanism is None:
        return matched_alerts, matched_news, matched_signals, matched_positions, matched_event_items, matched_event_links
    factor = filters.mechanism
    filtered_alerts = [
        row
        for row in matched_alerts
        if _factor_from_text(
            " ".join([row.title_zh or row.title, row.summary_zh or row.summary, row.type])
        )
        == factor
    ]
    filtered_news = [
        row
        for row in matched_news
        if _factor_from_text(
            " ".join(
                [
                    row.title_zh or row.title,
                    row.summary_zh or row.summary,
                    row.event_type,
                    row.direction,
                ]
            )
        )
        == factor
    ]
    filtered_signals = [row for row in matched_signals if _factor_from_text(row.signal_type) == factor]
    filtered_positions = matched_positions if factor == "demand_shift" else []
    filtered_links = [row for row in matched_event_links if _factor_from_event_intelligence_link(row) == factor]
    linked_event_ids = {row.event_item_id for row in filtered_links}
    filtered_items = [
        row
        for row in matched_event_items
        if row.id in linked_event_ids or _event_intelligence_item_matches_factor(row, factor)
    ]
    return filtered_alerts, filtered_news, filtered_signals, filtered_positions, filtered_items, filtered_links


def _filter_factor_signals(
    factor_signals: list[FactorSignal],
    filters: WorldMapFilterScope | None,
) -> list[FactorSignal]:
    if filters is None:
        return factor_signals
    filtered = factor_signals
    if filters.source != "all":
        filtered = [signal for signal in filtered if signal.evidence_kind == filters.source]
    if filters.mechanism is not None:
        filtered = [signal for signal in filtered if signal.factor == filters.mechanism]
    return filtered


def _event_intelligence_quality_reports(
    matched_items: list[EventIntelligenceItem],
    matched_links: list[EventImpactLink],
) -> dict[UUID, EventIntelligenceQualityRead]:
    links_by_event_id: dict[UUID, list[EventImpactLink]] = {item.id: [] for item in matched_items}
    for link in matched_links:
        links_by_event_id.setdefault(link.event_item_id, []).append(link)
    return {
        item.id: evaluate_event_intelligence_quality(item, links_by_event_id.get(item.id, []))
        for item in matched_items
    }


def _event_intelligence_link_quality_map(
    reports: dict[UUID, EventIntelligenceQualityRead],
) -> dict[UUID, EventImpactLinkQualityRead]:
    return {
        link_report.id: link_report
        for report in reports.values()
        for link_report in report.link_reports
    }


def _world_map_event_quality(
    reports: dict[UUID, EventIntelligenceQualityRead],
) -> WorldMapEventQuality:
    rows = list(reports.values())
    total = len(rows)
    if total == 0:
        return WorldMapEventQuality(
            status=None,
            score=0,
            total=0,
            blocked=0,
            review=0,
            shadowReady=0,
            decisionGrade=0,
            passed=0,
        )
    blocked = sum(1 for row in rows if row.status == "blocked")
    review = sum(1 for row in rows if row.status == "review")
    shadow_ready = sum(1 for row in rows if row.status == "shadow_ready")
    decision_grade = sum(1 for row in rows if row.status == "decision_grade")
    status = _dominant_event_quality_status(
        blocked=blocked,
        review=review,
        shadow_ready=shadow_ready,
        decision_grade=decision_grade,
    )
    return WorldMapEventQuality(
        status=status,
        score=round(sum(row.score for row in rows) / total),
        total=total,
        blocked=blocked,
        review=review,
        shadowReady=shadow_ready,
        decisionGrade=decision_grade,
        passed=shadow_ready + decision_grade,
    )


def _world_map_evidence_health(
    *,
    story: WorldMapRiskStory,
    adaptive_alerts: list[WorldMapAdaptiveAlert],
    runtime: WorldMapRuntime,
    weather: WorldMapWeather,
    event_quality: WorldMapEventQuality,
) -> WorldMapEvidenceHealth:
    evidence_count = len(story.evidence) + len(adaptive_alerts)
    counter_evidence_count = len(story.counterEvidence)
    runtime_source_counts = [
        runtime.alerts,
        runtime.newsEvents,
        runtime.signals,
        runtime.positions,
        runtime.eventIntelligence,
    ]
    runtime_sources = sum(1 for count in runtime_source_counts if count > 0)
    if weather.dataSource:
        runtime_sources += 1

    fresh_runtime_sources = 0
    if weather.dataSource != BASELINE_WEATHER_SOURCE:
        fresh_runtime_sources += 1
    event_freshness = _event_freshness_score(runtime.latestEventAt)
    if event_freshness >= 70:
        fresh_runtime_sources += sum(1 for count in runtime_source_counts if count > 0)

    total_runtime_rows = sum(runtime_source_counts)
    density_score = _clamp_int(
        round(
            evidence_count * 9
            + counter_evidence_count * 7
            + runtime_sources * 10
            + min(total_runtime_rows, 12) * 3
        ),
        0,
        100,
    )
    quality_component = event_quality.score if event_quality.total else 55
    source_reliability = _clamp_int(
        round(
            weather.confidence * 35
            + quality_component * 0.35
            + min(runtime_sources / 4, 1) * 20
            + min((evidence_count + counter_evidence_count) / 7, 1) * 10
        ),
        0,
        100,
    )
    weather_freshness = 72 if weather.dataSource != BASELINE_WEATHER_SOURCE else round(weather.confidence * 60)
    freshness_score = (
        round(event_freshness * 0.6 + weather_freshness * 0.4)
        if total_runtime_rows > 0
        else weather_freshness
    )
    return WorldMapEvidenceHealth(
        evidenceCount=evidence_count,
        counterEvidenceCount=counter_evidence_count,
        runtimeSources=runtime_sources,
        freshRuntimeSources=fresh_runtime_sources,
        sourceReliability=source_reliability,
        freshnessScore=_clamp_int(freshness_score, 0, 100),
        densityScore=density_score,
    )


def _world_map_risk_momentum(
    *,
    definition: RegionDefinition,
    runtime: WorldMapRuntime,
    weather: WorldMapWeather,
    event_quality: WorldMapEventQuality,
    evidence_health: WorldMapEvidenceHealth,
    factor_signals: list[FactorSignal],
) -> WorldMapRiskMomentum:
    primary = factor_signals[0] if factor_signals else None
    runtime_rows = (
        runtime.alerts
        + runtime.newsEvents
        + runtime.signals
        + runtime.positions
        + runtime.eventIntelligence
    )
    if runtime.eventIntelligence and event_quality.blocked > event_quality.passed:
        delta = -min(18, 4 + event_quality.blocked * 5 + event_quality.review * 2)
        return WorldMapRiskMomentum(
            direction="easing",
            delta=delta,
            intensity=round(min(abs(delta) / 28, 1.0), 2),
            driverZh="质量门阻断",
            driverEn="Quality gate blocked",
            reasonZh="事件智能未通过质量门，地图保留阅读但不放大风险动量。",
            reasonEn="Event intelligence failed the quality gate, so the map keeps it readable without amplifying momentum.",
            changedAt=runtime.latestEventAt,
        )

    weather_stress = max(
        abs(weather.precipitationAnomalyPct) / 55,
        weather.floodRisk,
        weather.droughtRisk,
    )
    raw_delta = (
        runtime.highSeverityAlerts * 7
        + runtime.alerts * 3
        + runtime.newsEvents * 2
        + runtime.signals * 2
        + runtime.positions
        + runtime.eventIntelligence * 2
        + event_quality.passed * 4
        + round(weather_stress * 6 if weather.dataSource != BASELINE_WEATHER_SOURCE else 0)
        + round(max(evidence_health.freshnessScore - 65, 0) / 12)
    )
    if runtime_rows == 0 and weather.dataSource == BASELINE_WEATHER_SOURCE:
        raw_delta = 0
    delta = _clamp_int(raw_delta, -100, 100)
    if delta >= 5:
        direction: RiskMomentumDirection = "rising"
    elif delta <= -5:
        direction = "easing"
    else:
        direction = "steady"

    if primary is not None:
        driver_zh = primary.label_zh
        driver_en = primary.label_en
    elif weather.dataSource != BASELINE_WEATHER_SOURCE:
        driver_zh = "天气异常更新"
        driver_en = "Weather anomaly update"
    else:
        driver_zh = "区域基线"
        driver_en = "Regional baseline"

    reason_zh, reason_en = _risk_momentum_reason(
        definition=definition,
        direction=direction,
        runtime=runtime,
        weather=weather,
        event_quality=event_quality,
        evidence_health=evidence_health,
    )
    return WorldMapRiskMomentum(
        direction=direction,
        delta=delta,
        intensity=round(min(abs(delta) / 32, 1.0), 2),
        driverZh=driver_zh,
        driverEn=driver_en,
        reasonZh=reason_zh,
        reasonEn=reason_en,
        changedAt=runtime.latestEventAt,
    )


def _risk_momentum_reason(
    *,
    definition: RegionDefinition,
    direction: RiskMomentumDirection,
    runtime: WorldMapRuntime,
    weather: WorldMapWeather,
    event_quality: WorldMapEventQuality,
    evidence_health: WorldMapEvidenceHealth,
) -> tuple[str, str]:
    if direction == "rising":
        reasons_zh: list[str] = []
        reasons_en: list[str] = []
        if runtime.highSeverityAlerts:
            reasons_zh.append(f"{runtime.highSeverityAlerts} 条高等级预警")
            reasons_en.append(f"{runtime.highSeverityAlerts} high-severity alert(s)")
        if runtime.eventIntelligence:
            reasons_zh.append(f"{event_quality.passed}/{event_quality.total} 条事件智能通过质量门")
            reasons_en.append(f"{event_quality.passed}/{event_quality.total} event-intelligence item(s) passed quality gates")
        if weather.dataSource != BASELINE_WEATHER_SOURCE:
            reasons_zh.append(f"天气数据源 {weather.dataSource} 已更新")
            reasons_en.append(f"weather source {weather.dataSource} updated")
        if not reasons_zh:
            reasons_zh.append("运行态信号与证据密度上升")
            reasons_en.append("runtime signals and evidence density increased")
        return (
            f"{definition.name_zh}风险升温：{'，'.join(reasons_zh)}。",
            f"{definition.name_en} momentum is rising: {', '.join(reasons_en)}.",
        )
    if direction == "easing":
        return (
            f"{definition.name_zh}动量降温：低质量事件被阻断或缺少新鲜运行态证据。",
            f"{definition.name_en} momentum is easing: weak events were blocked or fresh runtime evidence is missing.",
        )
    return (
        f"{definition.name_zh}暂无明显风险动量，当前主要作为基线观察。",
        f"{definition.name_en} has no clear risk momentum and is mainly a baseline watch.",
    )


def _event_freshness_score(timestamp: datetime | None) -> int:
    if timestamp is None:
        return 0
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_hours = max((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600, 0.0)
    if age_hours <= 6:
        return 100
    if age_hours <= 24:
        return 86
    if age_hours <= 72:
        return 68
    if age_hours <= 168:
        return 48
    return 25


def _dominant_event_quality_status(
    *,
    blocked: int,
    review: int,
    shadow_ready: int,
    decision_grade: int,
) -> EventQualityStatus:
    if decision_grade:
        return "decision_grade"
    if shadow_ready:
        return "shadow_ready"
    if review:
        return "review"
    if blocked:
        return "blocked"
    return "review"


def _event_quality_weight(status: EventQualityStatus | None) -> float:
    if status == "decision_grade":
        return 1.0
    if status == "shadow_ready":
        return 0.7
    if status == "review":
        return 0.18
    return 0.0


def _link_quality_weight(report: EventImpactLinkQualityRead | None) -> float:
    if report is None:
        return 0.0
    if report.status == "passed":
        return 1.0
    if report.status == "review":
        return 0.25
    return 0.0


def _event_intelligence_item_matches_factor(row: EventIntelligenceItem, factor: RiskFactor) -> bool:
    return any(_factor_from_text(str(mechanism)) == factor for mechanism in row.mechanisms or [])


def _factor_mechanisms(factor_signals: list[FactorSignal]) -> list[RiskFactor]:
    seen: set[RiskFactor] = set()
    mechanisms: list[RiskFactor] = []
    for signal in factor_signals:
        if signal.factor in seen:
            continue
        seen.add(signal.factor)
        mechanisms.append(signal.factor)
    return mechanisms


def _source_kinds(
    factor_signals: list[FactorSignal],
    *,
    matched_alerts: list[Alert],
    matched_news: list[NewsEvent],
    matched_signals: list[SignalTrack],
    matched_positions: list[Position],
    matched_event_items: list[EventIntelligenceItem],
) -> list[EvidenceKind]:
    ordered: list[EvidenceKind] = []
    for source in [signal.evidence_kind for signal in factor_signals]:
        if source not in ordered:
            ordered.append(source)
    for source, present in (
        ("alert", bool(matched_alerts)),
        ("news", bool(matched_news)),
        ("signal", bool(matched_signals)),
        ("position", bool(matched_positions)),
        ("event_intelligence", bool(matched_event_items)),
    ):
        if present and source not in ordered:
            ordered.append(source)
    return ordered


def _region_weather(
    definition: RegionDefinition,
    industry_weather: list[IndustryData],
) -> WorldMapWeather:
    seed = definition.baseline_weather
    latest = _latest_weather_rows(industry_weather, definition)
    current_temperature = _mean([row.value for row in _rows_for_type(latest, "weather_temp_current_c")])
    precipitation_1h = _mean([row.value for row in _rows_for_type(latest, "weather_precip_1h")])
    humidity = _mean([row.value for row in _rows_for_type(latest, "weather_humidity_pct")])
    wind = _mean([row.value for row in _rows_for_type(latest, "weather_wind_kph")])
    current_source_rows = [
        *_rows_for_type(latest, "weather_temp_current_c"),
        *_rows_for_type(latest, "weather_precip_1h"),
        *_rows_for_type(latest, "weather_humidity_pct"),
        *_rows_for_type(latest, "weather_wind_kph"),
    ]
    recent_precip_rows = _rows_for_type(latest, "weather_precip_7d")
    if not recent_precip_rows:
        has_current_rows = bool(current_source_rows)
        return WorldMapWeather(
            precipitationAnomalyPct=seed.precipitation_anomaly_pct,
            rainfall7dMm=seed.rainfall_7d_mm,
            temperatureAnomalyC=seed.temperature_anomaly_c,
            floodRisk=seed.flood_risk,
            droughtRisk=seed.drought_risk,
            precipitationPercentile=None,
            temperaturePercentile=None,
            currentTemperatureC=round(current_temperature, 2) if current_temperature is not None else None,
            precipitation1hMm=round(precipitation_1h, 2) if precipitation_1h is not None else None,
            humidityPct=round(humidity, 2) if humidity is not None else None,
            windKph=round(wind, 2) if wind is not None else None,
            dataSource=(
                _weather_source(current_source_rows, has_baseline_rows=False)
                if has_current_rows
                else BASELINE_WEATHER_SOURCE
            ),
            confidence=(
                _weather_confidence(
                    seed.confidence,
                    has_precip=False,
                    has_temperature=False,
                    has_baseline_rows=False,
                    has_percentile_rows=False,
                    has_current_rows=True,
                )
                if has_current_rows
                else seed.confidence
            ),
        )

    rainfall_7d_mm = _mean([row.value for row in recent_precip_rows])
    baseline_precip_rows = _rows_for_type(latest, "weather_baseline_precip_7d")
    baseline_precip = _mean([row.value for row in baseline_precip_rows])
    baseline_precip = baseline_precip if baseline_precip is not None and baseline_precip > 0 else seed.rainfall_7d_mm
    precipitation_anomaly_pct = _bounded_pct_change(rainfall_7d_mm, baseline_precip)
    precipitation_percentile = _mean([row.value for row in _rows_for_type(latest, "weather_precip_pctile_7d")])

    temp_max = _mean([row.value for row in _rows_for_type(latest, "weather_temp_max_7d")])
    temp_min = _mean([row.value for row in _rows_for_type(latest, "weather_temp_min_7d")])
    baseline_temp = _mean([row.value for row in _rows_for_type(latest, "weather_baseline_temp_mean_7d")])
    if temp_max is not None and temp_min is not None and baseline_temp is not None:
        temperature_anomaly_c = round(((temp_max + temp_min) / 2) - baseline_temp, 2)
    else:
        temperature_anomaly_c = seed.temperature_anomaly_c
    temperature_percentile = _mean([row.value for row in _rows_for_type(latest, "weather_temp_pctile_7d")])

    source_rows = [
        *recent_precip_rows,
        *_rows_for_type(latest, "weather_temp_max_7d"),
        *_rows_for_type(latest, "weather_temp_min_7d"),
        *_rows_for_type(latest, "weather_baseline_precip_7d"),
        *_rows_for_type(latest, "weather_baseline_temp_mean_7d"),
        *_rows_for_type(latest, "weather_precip_pctile_7d"),
        *_rows_for_type(latest, "weather_temp_pctile_7d"),
        *current_source_rows,
    ]
    has_baseline_rows = bool(baseline_precip_rows)
    has_percentile_rows = precipitation_percentile is not None or temperature_percentile is not None
    has_current_rows = bool(current_source_rows)
    source = _weather_source(source_rows, has_baseline_rows=has_baseline_rows)
    confidence = _weather_confidence(
        seed.confidence,
        has_precip=True,
        has_temperature=temp_max is not None and temp_min is not None,
        has_baseline_rows=has_baseline_rows,
        has_percentile_rows=has_percentile_rows,
        has_current_rows=has_current_rows,
    )

    return WorldMapWeather(
        precipitationAnomalyPct=precipitation_anomaly_pct,
        rainfall7dMm=round(rainfall_7d_mm, 2),
        temperatureAnomalyC=temperature_anomaly_c,
        floodRisk=_runtime_flood_risk(
            seed,
            precipitation_anomaly_pct,
            rainfall_7d_mm,
            baseline_precip,
            precipitation_percentile=precipitation_percentile,
        ),
        droughtRisk=_runtime_drought_risk(
            seed,
            precipitation_anomaly_pct,
            rainfall_7d_mm,
            baseline_precip,
            precipitation_percentile=precipitation_percentile,
        ),
        precipitationPercentile=round(precipitation_percentile, 2) if precipitation_percentile is not None else None,
        temperaturePercentile=round(temperature_percentile, 2) if temperature_percentile is not None else None,
        currentTemperatureC=round(current_temperature, 2) if current_temperature is not None else None,
        precipitation1hMm=round(precipitation_1h, 2) if precipitation_1h is not None else None,
        humidityPct=round(humidity, 2) if humidity is not None else None,
        windKph=round(wind, 2) if wind is not None else None,
        dataSource=source,
        confidence=confidence,
    )


def _latest_weather_rows(
    rows: list[IndustryData],
    definition: RegionDefinition,
) -> dict[tuple[str, str, str], IndustryData]:
    region_symbols = {_root_symbol(symbol) for symbol in definition.symbols}
    latest: dict[tuple[str, str, str], IndustryData] = {}
    for row in rows:
        symbol = _root_symbol(row.symbol)
        if row.data_type not in WORLD_MAP_WEATHER_DATA_TYPES:
            continue
        source_region = _weather_row_region(row.source)
        if source_region is not None:
            if source_region != definition.id:
                continue
        elif symbol not in region_symbols:
            continue
        key = (_weather_row_source_key(row.source, symbol), symbol, row.data_type)
        previous = latest.get(key)
        if previous is None or _weather_row_key(row) > _weather_row_key(previous):
            latest[key] = row
    return latest


def _weather_row_source_key(source: str, symbol: str) -> str:
    return source or symbol


def _weather_row_region(source: str) -> str | None:
    if ":" not in source:
        return None
    _, location_key = source.split(":", 1)
    return WEATHER_REGION_BY_LOCATION_KEY.get(location_key)


def _weather_row_key(row: IndustryData) -> tuple[datetime, datetime]:
    return row.timestamp, row.ingested_at or row.timestamp


def _rows_for_type(
    rows: dict[tuple[str, str, str], IndustryData],
    data_type: str,
) -> list[IndustryData]:
    return [row for key, row in rows.items() if key[-1] == data_type]


def _weather_source(rows: list[IndustryData], *, has_baseline_rows: bool) -> str:
    sources = sorted({_source_family(row.source) for row in rows if row.source})
    if not has_baseline_rows:
        sources.append(BASELINE_WEATHER_SOURCE)
    return "+".join(dict.fromkeys(sources)) if sources else BASELINE_WEATHER_SOURCE


def _source_family(source: str) -> str:
    return source.split(":", 1)[0]


def _weather_confidence(
    seed_confidence: float,
    *,
    has_precip: bool,
    has_temperature: bool,
    has_baseline_rows: bool,
    has_percentile_rows: bool,
    has_current_rows: bool,
) -> float:
    confidence = max(seed_confidence, 0.5)
    if has_precip:
        confidence += 0.1
    if has_temperature:
        confidence += 0.06
    if has_baseline_rows:
        confidence += 0.08
    if has_percentile_rows:
        confidence += 0.04
    if has_current_rows:
        confidence += 0.03
    return round(_clamp_float(confidence, 0.0, 0.86), 2)


def _runtime_flood_risk(
    seed: WeatherBaseline,
    anomaly_pct: float,
    rainfall_7d_mm: float,
    baseline_precip: float,
    *,
    precipitation_percentile: float | None = None,
) -> float:
    positive_anomaly = max(anomaly_pct, 0.0) / 100
    rain_load = min(rainfall_7d_mm / max(baseline_precip * 1.8, 1.0), 1.0)
    percentile_stress = _upper_percentile_stress(precipitation_percentile)
    return round(
        _clamp_float(
            seed.flood_risk * 0.3 + positive_anomaly * 0.62 + rain_load * 0.16 + percentile_stress * 0.42,
            0.0,
            1.0,
        ),
        2,
    )


def _runtime_drought_risk(
    seed: WeatherBaseline,
    anomaly_pct: float,
    rainfall_7d_mm: float,
    baseline_precip: float,
    *,
    precipitation_percentile: float | None = None,
) -> float:
    negative_anomaly = max(-anomaly_pct, 0.0) / 100
    dryness = max(0.0, 1 - rainfall_7d_mm / max(baseline_precip * 0.85, 1.0))
    percentile_stress = _lower_percentile_stress(precipitation_percentile)
    return round(
        _clamp_float(
            seed.drought_risk * 0.3 + negative_anomaly * 0.62 + dryness * 0.18 + percentile_stress * 0.42,
            0.0,
            1.0,
        ),
        2,
    )


def _upper_percentile_stress(value: float | None) -> float:
    if value is None:
        return 0.0
    return _clamp_float((value - 70) / 30, 0.0, 1.0)


def _lower_percentile_stress(value: float | None) -> float:
    if value is None:
        return 0.0
    return _clamp_float((30 - value) / 30, 0.0, 1.0)


def _bounded_pct_change(value: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0 if value <= 0 else 100.0
    return round(_clamp_float(((value - baseline) / baseline) * 100, -95.0, 180.0), 2)


def _mean(values: list[float]) -> float | None:
    numbers = [value for value in values if value is not None]
    return sum(numbers) / len(numbers) if numbers else None


def _world_map_layers(*, weather_runtime: bool = False) -> list[WorldMapLayer]:
    return [
        WorldMapLayer(
            id="weather",
            labelZh="天气异常",
            labelEn="Weather Anomaly",
            status="ready" if weather_runtime else "baseline",
            enabled=True,
        ),
        WorldMapLayer(id="alerts", labelZh="预警热力", labelEn="Alert Heat", status="ready", enabled=True),
        WorldMapLayer(id="causal", labelZh="因果联动", labelEn="Causal Linkage", status="ready", enabled=True),
        WorldMapLayer(id="positions", labelZh="持仓暴露", labelEn="Position Exposure", status="ready", enabled=True),
        WorldMapLayer(id="globe", labelZh="3D 地球", labelEn="3D Globe", status="planned", enabled=False),
    ]


def _build_world_map_tile_cells(
    regions: list[WorldMapRegion],
    *,
    layer: TileLayerFilter,
    resolution: TileResolution,
) -> list[WorldMapTileCell]:
    lat_step, lon_step, max_cells = _tile_resolution_spec(resolution)
    cells: dict[tuple[str, int, int], WorldMapTileCell] = {}

    for region in regions:
        if layer in {"all", "weather"}:
            _merge_tile_cells(
                cells,
                _region_weather_tile_cells(region, lat_step=lat_step, lon_step=lon_step),
            )
        if layer in {"all", "risk"}:
            _merge_tile_cells(
                cells,
                _region_risk_tile_cells(region, lat_step=lat_step, lon_step=lon_step),
            )

    return sorted(cells.values(), key=lambda cell: cell.intensity, reverse=True)[:max_cells]


def _world_map_tile_viewport(
    *,
    min_lat: float | None,
    max_lat: float | None,
    min_lon: float | None,
    max_lon: float | None,
) -> WorldMapTileViewport | None:
    values = (min_lat, max_lat, min_lon, max_lon)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(status_code=400, detail="tile viewport requires all four bounds")
    assert min_lat is not None
    assert max_lat is not None
    assert min_lon is not None
    assert max_lon is not None
    if min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="min_lat must be less than max_lat")
    if min_lon >= max_lon:
        raise HTTPException(status_code=400, detail="min_lon must be less than max_lon")
    return WorldMapTileViewport(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )


def _filter_tile_cells_for_viewport(
    cells: list[WorldMapTileCell],
    viewport: WorldMapTileViewport | None,
) -> list[WorldMapTileCell]:
    if viewport is None:
        return cells
    return [cell for cell in cells if _tile_cell_intersects_viewport(cell, viewport)]


def _tile_cell_intersects_viewport(
    cell: WorldMapTileCell,
    viewport: WorldMapTileViewport,
) -> bool:
    latitudes = [point.lat for point in cell.polygon]
    longitudes = [point.lon for point in cell.polygon]
    cell_min_lat = min(latitudes, default=cell.center.lat)
    cell_max_lat = max(latitudes, default=cell.center.lat)
    cell_min_lon = min(longitudes, default=cell.center.lon)
    cell_max_lon = max(longitudes, default=cell.center.lon)
    if cell_max_lat < viewport.min_lat or cell_min_lat > viewport.max_lat:
        return False
    if cell_max_lon < viewport.min_lon or cell_min_lon > viewport.max_lon:
        return False
    return True


def _tile_resolution_spec(resolution: TileResolution) -> tuple[float, float, int]:
    if resolution == "medium":
        return 4.0, 5.0, 520
    return 6.0, 8.0, 320


def _merge_tile_cells(
    cells: dict[tuple[str, int, int], WorldMapTileCell],
    next_cells: list[WorldMapTileCell],
) -> None:
    for cell in next_cells:
        _, _, lat_index, lon_index = cell.id.split(":")
        key = (cell.layer, int(lat_index), int(lon_index))
        previous = cells.get(key)
        if previous is None or previous.intensity < cell.intensity:
            cells[key] = cell


def _region_weather_tile_cells(
    region: WorldMapRegion,
    *,
    lat_step: float,
    lon_step: float,
) -> list[WorldMapTileCell]:
    anomaly_stress = min(abs(region.weather.precipitationAnomalyPct) / 85, 1.0)
    weather_stress = max(anomaly_stress, region.weather.floodRisk, region.weather.droughtRisk)
    radius = 1 + round(weather_stress * 2)
    metric, value = _dominant_weather_metric(region)
    cells: list[WorldMapTileCell] = []

    for row in range(-radius, radius + 1):
        for column in range(-radius, radius + 1):
            distance = (row * row + column * column) ** 0.5
            if distance > radius + 0.35:
                continue
            decay = 1 - distance / (radius + 0.85)
            intensity = max(0.0, min(weather_stress * (0.45 + decay * 0.55), 1.0))
            if intensity < 0.16:
                continue
            lat = region.center.lat + row * lat_step
            lon = region.center.lon + column * lon_step
            cells.append(
                _tile_cell(
                    layer="weather",
                    region=region,
                    lat=lat,
                    lon=lon,
                    lat_step=lat_step,
                    lon_step=lon_step,
                    metric=metric,
                    value=value,
                    intensity=intensity,
                    source=region.weather.dataSource,
                )
            )
    return cells


def _region_risk_tile_cells(
    region: WorldMapRegion,
    *,
    lat_step: float,
    lon_step: float,
) -> list[WorldMapTileCell]:
    risk_weight = region.riskScore / 100
    radius = 1 + round(risk_weight * 2)
    cells: list[WorldMapTileCell] = []

    for row in range(-radius, radius + 1):
        for column in range(-radius, radius + 1):
            distance = (row * row + column * column) ** 0.5
            if distance > radius + 0.35:
                continue
            decay = 1 - distance / (radius + 0.85)
            intensity = max(0.0, min(risk_weight * (0.5 + decay * 0.5), 1.0))
            if intensity < 0.18:
                continue
            lat = region.center.lat + row * lat_step
            lon = region.center.lon + column * lon_step
            cells.append(
                _tile_cell(
                    layer="risk",
                    region=region,
                    lat=lat,
                    lon=lon,
                    lat_step=lat_step,
                    lon_step=lon_step,
                    metric="composite_risk",
                    value=float(region.riskScore),
                    intensity=intensity,
                    source="world_map_runtime_score",
                )
            )
    return cells


def _dominant_weather_metric(region: WorldMapRegion) -> tuple[TileMetric, float]:
    anomaly_stress = min(abs(region.weather.precipitationAnomalyPct) / 85, 1.0)
    if region.weather.droughtRisk >= region.weather.floodRisk and region.weather.droughtRisk >= anomaly_stress:
        return "drought_risk", region.weather.droughtRisk
    if region.weather.floodRisk >= anomaly_stress:
        return "flood_risk", region.weather.floodRisk
    return "precipitation_anomaly_pct", region.weather.precipitationAnomalyPct


def _tile_cell(
    *,
    layer: TileLayer,
    region: WorldMapRegion,
    lat: float,
    lon: float,
    lat_step: float,
    lon_step: float,
    metric: TileMetric,
    value: float,
    intensity: float,
    source: str,
) -> WorldMapTileCell:
    lat_index = round(lat / lat_step)
    lon_index = round(lon / lon_step)
    center_lat = _clamp_float(lat_index * lat_step, -85.0, 85.0)
    center_lon = _clamp_float(lon_index * lon_step, -180.0, 180.0)
    half_lat = lat_step / 2
    half_lon = lon_step / 2
    south = _clamp_float(center_lat - half_lat, -85.0, 85.0)
    north = _clamp_float(center_lat + half_lat, -85.0, 85.0)
    west = _clamp_float(center_lon - half_lon, -180.0, 180.0)
    east = _clamp_float(center_lon + half_lon, -180.0, 180.0)

    return WorldMapTileCell(
        id=f"{layer}:{region.id}:{lat_index}:{lon_index}",
        layer=layer,
        regionId=region.id,
        center=GeoPoint(lat=center_lat, lon=center_lon),
        polygon=[
            GeoPoint(lat=south, lon=west),
            GeoPoint(lat=south, lon=east),
            GeoPoint(lat=north, lon=east),
            GeoPoint(lat=north, lon=west),
        ],
        metric=metric,
        value=value,
        intensity=round(intensity, 4),
        riskLevel=region.riskLevel,
        dataQuality=region.dataQuality,
        source=source,
    )


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


def _commodity_lens(definition: RegionDefinition) -> CommodityLens:
    if "rubber" in definition.id:
        return COMMODITY_LENSES["rubber"]
    if "crude" in definition.id:
        return COMMODITY_LENSES["energy"]
    if "ferrous" in definition.id or "iron" in definition.id:
        return COMMODITY_LENSES["ferrous"]
    if "grains" in definition.id:
        return COMMODITY_LENSES["agri_energy"]
    if "agri" in definition.id:
        return COMMODITY_LENSES["agri"]
    return COMMODITY_LENSES["rubber"]


def _factor_signals(
    definition: RegionDefinition,
    *,
    lens: CommodityLens,
    matched_alerts: list[Alert],
    matched_news: list[NewsEvent],
    matched_signals: list[SignalTrack],
    matched_positions: list[Position],
    matched_event_links: list[EventImpactLink],
    event_link_quality_by_id: dict[UUID, EventImpactLinkQualityRead],
    weather: WorldMapWeather,
    weather_risk: float,
) -> list[FactorSignal]:
    signals: list[FactorSignal] = []
    weather_factor = _weather_factor(definition, weather, lens.default_factor)
    signals.append(
        FactorSignal(
            factor=weather_factor,
            weight=min(max(weather_risk, 0.25), 1.0),
            evidence_kind="weather",
            label_zh=_factor_label_zh(weather_factor),
            label_en=_factor_label_en(weather_factor),
            source=weather.dataSource,
        )
    )
    for row in matched_alerts[:8]:
        title = row.title_zh or row.title
        summary = row.summary_zh or row.summary
        factor = _factor_from_text(" ".join([title, summary, row.type]))
        signals.append(
            FactorSignal(
                factor=factor,
                weight=min(max(row.confidence, 0.35), 1.0),
                evidence_kind="alert",
                label_zh=title[:40],
                label_en=_english_hint(row.type, row.category),
                source=f"alert:{row.id}",
            )
        )
    for row in matched_news[:8]:
        title = row.title_zh or row.title
        summary = row.summary_zh or row.summary
        factor = _factor_from_text(
            " ".join([title, summary, row.event_type, row.direction])
        )
        signals.append(
            FactorSignal(
                factor=factor,
                weight=min(max(row.llm_confidence, row.severity / 5), 1.0),
                evidence_kind="news",
                label_zh=title[:40],
                label_en=(row.title_original or row.title)[:80],
                source=f"news:{row.id}",
            )
        )
    for row in matched_signals[:8]:
        factor = _factor_from_text(row.signal_type)
        signals.append(
            FactorSignal(
                factor=factor,
                weight=min(max(row.confidence, 0.3), 1.0),
                evidence_kind="signal",
                label_zh=f"{row.signal_type} 信号",
                label_en=f"{row.signal_type} signal",
                source=f"signal:{row.id}",
            )
        )
    for row in matched_event_links[:8]:
        link_quality = event_link_quality_by_id.get(row.id)
        link_weight = _link_quality_weight(link_quality)
        if link_weight <= 0:
            continue
        factor = _factor_from_event_intelligence_link(row)
        signals.append(
            FactorSignal(
                factor=factor,
                weight=min(max(row.confidence, row.impact_score / 100, 0.35) * link_weight, 1.0),
                evidence_kind="event_intelligence",
                label_zh=_event_intelligence_factor_label_zh(row, factor),
                label_en=_event_intelligence_factor_label_en(row, factor),
                source=f"event_intelligence:{row.event_item_id}:{row.id}",
            )
        )
    if matched_positions:
        signals.append(
            FactorSignal(
                factor="demand_shift",
                weight=min(0.35 + len(matched_positions) * 0.12, 1.0),
                evidence_kind="position",
                label_zh="持仓暴露放大价格敏感度",
                label_en="Position exposure amplifies price sensitivity",
                source="positions",
            )
        )
    return _dedupe_factor_signals(signals)


def _weather_factor(
    definition: RegionDefinition,
    weather: WorldMapWeather,
    fallback: RiskFactor,
) -> RiskFactor:
    text = f"{definition.id} {definition.narrative_zh} {definition.narrative_en}"
    if "el_nino" in text or "厄尔尼诺" in text:
        return "el_nino"
    if weather.floodRisk >= 0.5 or weather.precipitationAnomalyPct >= 10:
        return "rainfall_surplus"
    if weather.droughtRisk >= 0.5 or weather.precipitationAnomalyPct <= -10:
        return "drought_heat"
    return fallback


def _factor_from_text(text: str) -> RiskFactor:
    normalized = text.lower()
    if _contains_any(normalized, ("el nino", "enso", "厄尔尼诺")):
        return "el_nino"
    if _contains_any(normalized, ("flood", "rain", "precip", "typhoon", "洪涝", "降水", "暴雨", "台风")):
        return "rainfall_surplus"
    if _contains_any(normalized, ("drought", "heat", "高温", "干旱", "少雨")):
        return "drought_heat"
    if _contains_any(normalized, ("port", "ship", "freight", "transport", "logistics", "港口", "航运", "运输", "物流")):
        return "logistics_disruption"
    if _contains_any(normalized, ("supply", "output", "production", "disruption", "供应", "产量", "停产", "扰动")):
        return "supply_disruption"
    if _contains_any(normalized, ("inventory", "stock", "库存", "仓单")):
        return "inventory_pressure"
    if _contains_any(normalized, ("policy", "quota", "sanction", "环保", "政策", "制裁", "限产")):
        return "policy_shift"
    if _contains_any(normalized, ("demand", "consumption", "需求", "消费", "开工")):
        return "demand_shift"
    if _contains_any(normalized, ("energy", "crude", "oil", "gas", "能源", "原油", "燃料")):
        return "energy_cost"
    return "supply_disruption"


def _factor_from_event_intelligence_link(row: EventImpactLink) -> RiskFactor:
    normalized = row.mechanism.lower().strip()
    mechanism_map: dict[str, RiskFactor] = {
        "weather": "rainfall_surplus",
        "climate": "rainfall_surplus",
        "supply": "supply_disruption",
        "logistics": "logistics_disruption",
        "transport": "logistics_disruption",
        "inventory": "inventory_pressure",
        "policy": "policy_shift",
        "demand": "demand_shift",
        "cost": "energy_cost",
        "energy": "energy_cost",
        "geopolitical": "supply_disruption",
        "risk_sentiment": "demand_shift",
        "macro": "demand_shift",
    }
    return mechanism_map.get(normalized, _factor_from_text(f"{row.mechanism} {row.rationale}"))


def _event_intelligence_factor_label_zh(row: EventImpactLink, factor: RiskFactor) -> str:
    symbol = _root_symbol(row.symbol)
    return f"{symbol} {_factor_label_zh(factor)}"


def _event_intelligence_factor_label_en(row: EventImpactLink, factor: RiskFactor) -> str:
    symbol = _root_symbol(row.symbol)
    return f"{symbol} {_factor_label_en(factor)}"


def _dedupe_factor_signals(signals: list[FactorSignal]) -> list[FactorSignal]:
    best_by_factor: dict[RiskFactor, FactorSignal] = {}
    for signal in signals:
        current = best_by_factor.get(signal.factor)
        if current is None or signal.weight > current.weight:
            best_by_factor[signal.factor] = signal
    return sorted(best_by_factor.values(), key=lambda item: item.weight, reverse=True)


def _risk_story(
    definition: RegionDefinition,
    lens: CommodityLens,
    factor_signals: list[FactorSignal],
    runtime: WorldMapRuntime,
) -> WorldMapRiskStory:
    primary = factor_signals[0] if factor_signals else FactorSignal(
        factor=lens.default_factor,
        weight=0.35,
        evidence_kind="baseline",
        label_zh=f"{lens.label_zh}基线扰动",
        label_en=f"{lens.label_en} baseline disturbance",
        source="baseline",
    )
    chain = _story_chain(lens, primary)
    evidence = [
        WorldMapEvidenceItem(
            kind=signal.evidence_kind,
            titleZh=signal.label_zh,
            titleEn=signal.label_en,
            source=signal.source,
            weight=signal.weight,
        )
        for signal in factor_signals[:6]
    ]
    if not evidence:
        evidence = [
            WorldMapEvidenceItem(
                kind="baseline",
                titleZh="区域商品基线规则",
                titleEn="Regional commodity baseline rule",
                source="baseline",
                weight=0.3,
            )
        ]
    counter_zh, counter_en = lens.counter_templates.get(
        primary.factor,
        GENERIC_COUNTER_TEMPLATES[primary.factor],
    )
    counter_evidence = [
        WorldMapEvidenceItem(
            kind="baseline",
            titleZh=counter_zh,
            titleEn=counter_en,
            source="counter_template",
            weight=0.45,
        )
    ]
    headline_zh = f"{definition.name_zh}：{primary.label_zh}正在影响{lens.label_zh}链路"
    headline_en = f"{definition.name_en}: {primary.label_en} is shaping the {lens.label_en} chain"
    if runtime.alerts or runtime.newsEvents or runtime.signals or runtime.eventIntelligence:
        headline_zh = f"{definition.name_zh}出现运行态风险：{primary.label_zh}"
        headline_en = f"{definition.name_en} has runtime risk: {primary.label_en}"
    return WorldMapRiskStory(
        headlineZh=headline_zh,
        headlineEn=headline_en,
        triggerZh=primary.label_zh,
        triggerEn=primary.label_en,
        chain=chain,
        evidence=evidence,
        counterEvidence=counter_evidence,
    )


def _story_chain(lens: CommodityLens, primary: FactorSignal) -> list[WorldMapStoryStep]:
    templates = lens.factor_steps.get(primary.factor)
    if not templates:
        templates = lens.factor_steps.get(lens.default_factor, ())
    return [
        WorldMapStoryStep(
            stage=stage,
            labelZh=label_zh,
            labelEn=label_en,
            confidence=max(0.25, min(primary.weight - index * 0.08, 1.0)),
            evidenceKind=primary.evidence_kind,
        )
        for index, (stage, label_zh, label_en) in enumerate(templates)
    ]


def _adaptive_alerts(
    definition: RegionDefinition,
    *,
    story: WorldMapRiskStory,
    factor_signals: list[FactorSignal],
    risk_score: int,
    runtime: WorldMapRuntime,
) -> list[WorldMapAdaptiveAlert]:
    alerts: list[WorldMapAdaptiveAlert] = []
    severity = _risk_level(risk_score)
    for index, signal in enumerate(factor_signals[:3]):
        chain_tail = story.chain[-1] if story.chain else None
        mechanism_zh = chain_tail.labelZh if chain_tail else definition.narrative_zh
        mechanism_en = chain_tail.labelEn if chain_tail else definition.narrative_en
        source: EvidenceKind = signal.evidence_kind
        if source == "weather" and (runtime.alerts or runtime.newsEvents or runtime.eventIntelligence):
            source = "alert" if runtime.alerts else "news" if runtime.newsEvents else "event_intelligence"
        alerts.append(
            WorldMapAdaptiveAlert(
                id=f"{definition.id}:{signal.factor}:{index}",
                titleZh=f"{definition.commodity_zh}：{signal.label_zh}",
                titleEn=f"{definition.commodity_en}: {signal.label_en}",
                severity=severity,
                triggerZh=signal.label_zh,
                triggerEn=signal.label_en,
                mechanismZh=mechanism_zh,
                mechanismEn=mechanism_en,
                confidence=signal.weight,
                source=source,
            )
        )
    return alerts


def _region_drivers(
    definition: RegionDefinition,
    runtime: WorldMapRuntime,
    factor_signals: list[FactorSignal],
) -> list[WorldMapDriver]:
    drivers = [
        WorldMapDriver(labelZh=signal.label_zh, labelEn=signal.label_en, weight=signal.weight)
        for signal in factor_signals[:3]
    ]
    if runtime.highSeverityAlerts:
        drivers.append(
            WorldMapDriver(labelZh="高等级预警", labelEn="High severity alerts", weight=min(runtime.highSeverityAlerts / 4, 1.0))
        )
    if runtime.newsEvents:
        drivers.append(
            WorldMapDriver(labelZh="新闻事件", labelEn="News events", weight=min(runtime.newsEvents / 8, 1.0))
        )
    if runtime.eventIntelligence:
        drivers.append(
            WorldMapDriver(
                labelZh="事件智能链路",
                labelEn="Event intelligence links",
                weight=min(runtime.eventIntelligence / 6, 1.0),
            )
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


def _data_quality(runtime: WorldMapRuntime, weather: WorldMapWeather) -> DataQuality:
    if runtime.alerts or runtime.newsEvents or runtime.signals or runtime.positions or runtime.eventIntelligence:
        return "runtime"
    if weather.dataSource != BASELINE_WEATHER_SOURCE:
        return "partial"
    return "baseline"


def _contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    return any(candidate in text for candidate in candidates)


def _factor_label_zh(factor: RiskFactor) -> str:
    labels: dict[RiskFactor, str] = {
        "rainfall_surplus": "降水异常 / 洪涝风险",
        "drought_heat": "高温少雨 / 干旱风险",
        "el_nino": "厄尔尼诺概率变化",
        "supply_disruption": "供应扰动",
        "logistics_disruption": "运输与港口扰动",
        "inventory_pressure": "库存缓冲变化",
        "policy_shift": "政策口径变化",
        "demand_shift": "需求预期变化",
        "energy_cost": "能源成本变化",
    }
    return labels[factor]


def _factor_label_en(factor: RiskFactor) -> str:
    labels: dict[RiskFactor, str] = {
        "rainfall_surplus": "Rainfall anomaly / flood risk",
        "drought_heat": "Heat and drought risk",
        "el_nino": "El Nino probability shift",
        "supply_disruption": "Supply disruption",
        "logistics_disruption": "Transport and port disruption",
        "inventory_pressure": "Inventory buffer change",
        "policy_shift": "Policy shift",
        "demand_shift": "Demand expectation shift",
        "energy_cost": "Energy cost change",
    }
    return labels[factor]


def _english_hint(signal_type: str, category: str) -> str:
    return f"{signal_type.replace('_', ' ')} / {category}"


def _alert_symbols(alert: Alert) -> set[str]:
    values = {str(value).upper() for value in (alert.related_assets or [])}
    values.update(_extract_symbol_tokens(alert.title))
    values.update(_extract_symbol_tokens(alert.summary))
    values.update(_extract_symbol_tokens(alert.title_zh or ""))
    values.update(_extract_symbol_tokens(alert.summary_zh or ""))
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


def _matched_event_intelligence_items(
    definition: RegionDefinition,
    rows: list[EventIntelligenceItem],
) -> list[EventIntelligenceItem]:
    region_symbols = set(definition.symbols)
    matched: list[EventIntelligenceItem] = []
    for row in rows:
        symbols = {str(symbol).upper() for symbol in row.symbols or []}
        regions = {str(region) for region in row.regions or []}
        if definition.id in regions or _symbols_intersect(symbols, region_symbols):
            matched.append(row)
    return matched


def _unique_recent_event_intelligence(
    rows: list[EventIntelligenceItem],
    *,
    limit: int,
) -> list[EventIntelligenceItem]:
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    unique: list[EventIntelligenceItem] = []
    for row in rows:
        key = _event_intelligence_display_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


def _event_intelligence_display_key(row: EventIntelligenceItem) -> tuple[str, tuple[str, ...], str]:
    symbols = tuple(sorted(str(symbol).upper() for symbol in (row.symbols or [])[:5]))
    return (row.event_type.lower(), symbols, _normalize_event_title(row.title))


def _normalize_event_title(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^\s*\([^)]*\)\s*", "", normalized)
    normalized = re.sub(r"^\s*feature\s*:\s*", "", normalized)
    normalized = normalized.split("--", 1)[0]
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return " ".join(normalized.split())


def _matched_event_intelligence_links(
    definition: RegionDefinition,
    matched_items: list[EventIntelligenceItem],
    rows: list[EventImpactLink],
) -> list[EventImpactLink]:
    matched_item_ids = {row.id for row in matched_items}
    region_symbols = set(definition.symbols)
    matched: list[EventImpactLink] = []
    seen: set[str] = set()
    for row in rows:
        symbol_match = _symbols_intersect({row.symbol}, region_symbols)
        region_match = row.region_id == definition.id
        item_match = row.event_item_id in matched_item_ids
        if not ((item_match and (symbol_match or region_match or row.region_id is None)) or symbol_match or region_match):
            continue
        key = str(row.id)
        if key in seen:
            continue
        seen.add(key)
        matched.append(row)
    return sorted(matched, key=lambda row: (row.impact_score, row.confidence), reverse=True)


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
    event_items: list[EventIntelligenceItem] | None = None,
) -> datetime | None:
    timestamps: list[datetime] = []
    timestamps.extend(row.triggered_at for row in alerts if row.triggered_at)
    timestamps.extend(row.published_at for row in news if row.published_at)
    timestamps.extend(row.created_at for row in signals if row.created_at)
    timestamps.extend(row.event_timestamp for row in event_items or [] if row.event_timestamp)
    if not timestamps:
        return None
    return max(timestamps)


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
