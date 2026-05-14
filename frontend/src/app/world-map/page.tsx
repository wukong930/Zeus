"use client";

import Link from "next/link";
import DeckGL from "@deck.gl/react";
import { COORDINATE_SYSTEM, OrthographicView } from "@deck.gl/core";
import { ArcLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { GeoJSONSource, Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { geoEqualEarth, geoGraticule, geoPath, type GeoPermissibleObjects, type GeoProjection } from "d3-geo";
import type {
  ComponentType,
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  WheelEvent as ReactWheelEvent,
} from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CloudRain,
  Compass,
  DatabaseZap,
  GitBranch,
  Globe2,
  Layers3,
  Link2,
  ListChecks,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Route,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Sparkles,
  X,
} from "lucide-react";
import { feature, mesh } from "topojson-client";
import type { GeometryObject, Topology } from "topojson-specification";
import type { FeatureCollection, GeometryObject as GeoJsonGeometryObject, MultiLineString } from "geojson";
import worldAtlas from "world-atlas/countries-110m.json";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import type { DataSourceState } from "@/components/DataSourceBadge";
import {
  fetchWorldMapTiles,
  fetchWorldMapSnapshot,
  type WorldMapFilterParams,
  type GeoPoint,
  type WorldMapAdaptiveAlert,
  type WorldMapFilterOption,
  type WorldMapLayer,
  type WorldMapRegion,
  type WorldMapRiskMomentum,
  type WorldMapRiskMomentumDirection,
  type WorldMapSnapshot,
  type WorldMapStoryStep,
  type WorldMapTileCell,
  type WorldMapTileResolution,
  type WorldMapTileSnapshot,
  type WorldMapViewport,
  type WorldRiskLevel,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  appendWorldMapNavigationScope,
  normalizeNavigationSymbol,
  normalizeWorldMapMechanismFilter,
  normalizeWorldMapSourceFilter,
} from "@/lib/navigation-scope";
import { cn } from "@/lib/utils";

type ScopeFilterValue = "all" | string;
type WorldMapScopeFilters = {
  symbol: ScopeFilterValue;
  mechanism: ScopeFilterValue;
  source: ScopeFilterValue;
};
type WorldMapVisualLayer = "weather" | "density" | "heat" | "routes" | "labels";
type WorldMapRendererMode = "svg" | "webgl-ready";
type VisibleMapLayers = Record<WorldMapVisualLayer, boolean>;
type MapFocusRequest = {
  nonce: number;
  regionId: string;
};
type TileRuntimeStatus = "cache_hit" | "network_miss" | "forced_refresh";
type TileRuntimeBudget = "light" | "normal" | "dense";
type TileRuntimeMetrics = {
  budget: TileRuntimeBudget;
  cacheEntries: number;
  resolution: WorldMapTileResolution;
  riskCells: number;
  status: TileRuntimeStatus;
  totalCells: number;
  weatherCells: number;
};
type RiskDensityCell = {
  id: string;
  x: number;
  y: number;
  size: number;
  intensity: number;
  riskLevel: WorldRiskLevel;
  regionId: string;
};
type ProjectedTileCell = {
  polygon: Array<[number, number, number]>;
};
type RiskRoute = {
  id: string;
  from: GeoPoint;
  to: GeoPoint;
  weight: number;
};
type RiskBridge = {
  id: string;
  source: WorldMapRegion;
  target: WorldMapRegion;
  sharedSymbols: string[];
  sharedCommodity: boolean;
  weight: number;
};
type RegionMapLabel = {
  anchorX: number;
  anchorY: number;
  height: number;
  id: string;
  priority: number;
  width: number;
  x: number;
  y: number;
};
type ScreenBox = {
  bottom: number;
  left: number;
  right: number;
  top: number;
};
type WeatherTileCell = {
  id: string;
  polygon: Array<[number, number, number]>;
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
  intensity: number;
  regionId: string;
};
type WebGlRegionPolygon = {
  id: string;
  polygon: Array<[number, number, number]>;
  fillColor: [number, number, number, number];
  lineColor: [number, number, number, number];
};
type WebGlRoute = {
  id: string;
  from: [number, number, number];
  to: [number, number, number];
  weight: number;
};
type TileRenderBudgetSpec = {
  densityCells: number;
  routes: number;
  weatherCells: number;
};
type MapLibreRuntimeStatus = "loading" | "ready" | "error";
type MapLibreRegionFeatureCollection = FeatureCollection<
  GeoJsonGeometryObject,
  {
    id: string;
    riskLevel: WorldRiskLevel;
    riskScore: number;
  }
>;

const MAP_WIDTH = 1000;
const MAP_HEIGHT = 560;
const WORLD_MAP_REFRESH_INTERVAL_MS = 30_000;
const WORLD_MAP_TILE_REFRESH_DEBOUNCE_MS = 360;
const WORLD_MAP_TILE_CACHE_LIMIT = 24;
const WORLD_MAP_TILE_RENDER_BUDGETS: Record<TileRuntimeBudget, TileRenderBudgetSpec> = {
  light: { densityCells: 220, routes: 10, weatherCells: 260 },
  normal: { densityCells: 170, routes: 8, weatherCells: 200 },
  dense: { densityCells: 120, routes: 6, weatherCells: 150 },
};
const WORLD_MAP_LABEL_SIZE = { height: 42, width: 154 };
const WORLD_MAP_LABEL_SAFE_AREA = {
  bottom: MAP_HEIGHT - 22,
  left: 22,
  right: MAP_WIDTH - 22,
  top: 118,
};
const WORLD_MAP_LABEL_BUDGETS: Record<TileRuntimeBudget, number> = {
  light: 12,
  normal: 8,
  dense: 5,
};
const MIN_MAP_SCALE = 0.85;
const MAX_MAP_SCALE = 3.25;
const DEFAULT_MAP_LAYERS: VisibleMapLayers = {
  weather: true,
  density: true,
  heat: true,
  routes: true,
  labels: true,
};
const MAP_RENDERER_OPTIONS: Array<{
  id: WorldMapRendererMode;
  label: string;
  detail: string;
}> = [
  { id: "svg", label: "轻量", detail: "SVG 主渲染" },
  { id: "webgl-ready", label: "增强", detail: "WebGL 预备" },
];

type WorldAtlasTopology = Topology<{
  countries: GeometryObject;
  land: GeometryObject;
}>;

type MapViewTransform = {
  scale: number;
  x: number;
  y: number;
};

const INITIAL_MAP_VIEW: MapViewTransform = { scale: 1, x: 0, y: 0 };

const WORLD_TOPOLOGY = worldAtlas as unknown as WorldAtlasTopology;
const WORLD_COUNTRIES = feature(
  WORLD_TOPOLOGY,
  WORLD_TOPOLOGY.objects.countries
) as FeatureCollection<GeoJsonGeometryObject>;
const WORLD_BORDERS = mesh(
  WORLD_TOPOLOGY,
  WORLD_TOPOLOGY.objects.countries,
  (a, b) => a !== b
) as MultiLineString;
const WORLD_GRATICULE = geoGraticule().step([30, 20])();
const MAP_VISUAL_LAYER_OPTIONS: Array<{
  id: WorldMapVisualLayer;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { id: "weather", label: "天气", icon: CloudRain },
  { id: "density", label: "密度", icon: Layers3 },
  { id: "heat", label: "热力", icon: AlertTriangle },
  { id: "routes", label: "飞线", icon: Route },
  { id: "labels", label: "地图标签", icon: ListChecks },
];

function initialWorldMapSearchParams() {
  if (typeof window === "undefined") return new URLSearchParams();
  return new URLSearchParams(window.location.search);
}

function initialWorldMapScopeFilters(): WorldMapScopeFilters {
  const params = initialWorldMapSearchParams();
  const symbol = normalizeNavigationSymbol(params.get("symbol"));
  const mechanism = normalizeWorldMapMechanismFilter(params.get("mechanism"));
  const source = normalizeWorldMapSourceFilter(params.get("source"));

  return {
    symbol: symbol || "all",
    mechanism: mechanism || "all",
    source: source || "all",
  };
}

function initialWorldMapRegionParam() {
  return initialWorldMapSearchParams().get("region")?.trim() || null;
}

function initialWorldMapEventParam() {
  return initialWorldMapSearchParams().get("event")?.trim() || null;
}

export default function WorldMapPage() {
  const { text } = useI18n();
  const [snapshot, setSnapshot] = useState<WorldMapSnapshot | null>(null);
  const [tileSnapshot, setTileSnapshot] = useState<WorldMapTileSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [scopeFilters, setScopeFilters] = useState<WorldMapScopeFilters>({
    symbol: "all",
    mechanism: "all",
    source: "all",
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [riskDeltas, setRiskDeltas] = useState<Record<string, number>>({});
  const [visibleLayers, setVisibleLayers] = useState<VisibleMapLayers>(DEFAULT_MAP_LAYERS);
  const [rendererMode, setRendererMode] = useState<WorldMapRendererMode>("svg");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [focusRequest, setFocusRequest] = useState<MapFocusRequest | null>(null);
  const [scopedEventId] = useState<string | null>(() => initialWorldMapEventParam());
  const [initialScopeReady, setInitialScopeReady] = useState(false);
  const [tileRuntime, setTileRuntime] = useState<TileRuntimeMetrics | null>(null);
  const snapshotRef = useRef<WorldMapSnapshot | null>(null);
  const tileSnapshotRef = useRef<WorldMapTileSnapshot | null>(null);
  const tileViewportRef = useRef<WorldMapViewport | null>(null);
  const tileCacheRef = useRef<Map<string, WorldMapTileSnapshot>>(new Map());
  const tileRequestSeqRef = useRef(0);
  const riskScoresRef = useRef<Record<string, number>>({});
  const mountedRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const tileRefreshTimerRef = useRef<number | null>(null);
  const initialScopeAppliedRef = useRef(false);

  const fetchTiles = useCallback(
    async ({
      resolution,
      viewport,
      force = false,
    }: {
      resolution: WorldMapTileResolution;
      viewport?: WorldMapViewport | null;
      force?: boolean;
    }) => {
      const cacheKey = worldMapTileCacheKey(scopeFilters, resolution, viewport);
      const cached = tileCacheRef.current.get(cacheKey);
      if (cached && !force) {
        setTileRuntime(buildTileRuntimeMetrics(cached, tileCacheRef.current.size, resolution, "cache_hit"));
        return cached;
      }

      const nextTileSnapshot = await fetchWorldMapTiles(
        "all",
        resolution,
        worldMapFilterParams(scopeFilters, viewport)
      );
      rememberWorldMapTileSnapshot(tileCacheRef.current, cacheKey, nextTileSnapshot);
      setTileRuntime(
        buildTileRuntimeMetrics(
          nextTileSnapshot,
          tileCacheRef.current.size,
          resolution,
          force ? "forced_refresh" : "network_miss"
        )
      );
      return nextTileSnapshot;
    },
    [scopeFilters]
  );

  const loadSnapshot = useCallback(async () => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    setIsRefreshing(true);
    const tileRequestId = ++tileRequestSeqRef.current;
    try {
      const filterParams = worldMapFilterParams(scopeFilters);
      const next = await fetchWorldMapSnapshot(filterParams);
      const nextTileSnapshot = await fetchTiles({
        resolution: "coarse",
        viewport: tileViewportRef.current,
        force: true,
      }).catch(() => tileSnapshotRef.current);
      if (!mountedRef.current) return;

      const previousScores = riskScoresRef.current;
      const nextScores = Object.fromEntries(next.regions.map((region) => [region.id, region.riskScore]));
      if (Object.keys(previousScores).length > 0) {
        setRiskDeltas(
          Object.fromEntries(
            next.regions
              .map((region) => [region.id, region.riskScore - (previousScores[region.id] ?? region.riskScore)] as const)
              .filter(([, delta]) => delta !== 0)
          )
        );
      }
      riskScoresRef.current = nextScores;
      snapshotRef.current = next;
      setSnapshot(next);
      if (tileRequestId === tileRequestSeqRef.current) {
        tileSnapshotRef.current = nextTileSnapshot;
        setTileSnapshot(nextTileSnapshot);
      }
      setSource(next.summary.runtimeLinkedRegions > 0 ? "api" : "partial");
      setLastUpdatedAt(new Date());
    } catch {
      if (!mountedRef.current) return;
      if (!snapshotRef.current) {
        setSnapshot(null);
        setSource("fallback");
      } else {
        setSource("partial");
      }
    } finally {
      refreshInFlightRef.current = false;
      if (mountedRef.current) setIsRefreshing(false);
    }
  }, [fetchTiles, scopeFilters]);

  const loadViewportTiles = useCallback(
    (viewport: WorldMapViewport, scale: number) => {
      tileViewportRef.current = viewport;
      if (tileRefreshTimerRef.current !== null) {
        window.clearTimeout(tileRefreshTimerRef.current);
      }
      tileRefreshTimerRef.current = window.setTimeout(() => {
        if (!mountedRef.current) return;
        const requestId = ++tileRequestSeqRef.current;
        const resolution = scale >= 1.35 ? "medium" : "coarse";
        fetchTiles({ resolution, viewport })
          .then((nextTileSnapshot) => {
            if (!mountedRef.current || requestId !== tileRequestSeqRef.current) return;
            tileSnapshotRef.current = nextTileSnapshot;
            setTileSnapshot(nextTileSnapshot);
          })
          .catch(() => undefined);
      }, WORLD_MAP_TILE_REFRESH_DEBOUNCE_MS);
    },
    [fetchTiles]
  );

  useEffect(() => {
    if (initialScopeAppliedRef.current) return;
    initialScopeAppliedRef.current = true;

    const nextFilters = initialWorldMapScopeFilters();
    const regionId = initialWorldMapRegionParam();
    const hasScopedFilter = Object.values(nextFilters).some((value) => value !== "all");

    if (hasScopedFilter) {
      setScopeFilters(nextFilters);
    }
    if (regionId) {
      setSelectedId(regionId);
      setDetailOpen(true);
      setFocusRequest({ regionId, nonce: 0 });
    }
    setInitialScopeReady(true);
  }, []);

  useEffect(() => {
    if (!initialScopeReady) return undefined;
    mountedRef.current = true;
    void loadSnapshot();
    return () => {
      mountedRef.current = false;
      if (tileRefreshTimerRef.current !== null) {
        window.clearTimeout(tileRefreshTimerRef.current);
        tileRefreshTimerRef.current = null;
      }
    };
  }, [initialScopeReady, loadSnapshot]);

  useEffect(() => {
    if (!initialScopeReady || !autoRefresh) return undefined;
    const timer = window.setInterval(() => {
      void loadSnapshot();
    }, WORLD_MAP_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh, initialScopeReady, loadSnapshot]);

  const regions = snapshot?.regions ?? [];
  const filteredRegions = regions;
  const filteredRegionIds = useMemo(
    () => new Set(filteredRegions.map((region) => region.id)),
    [filteredRegions]
  );
  const filteredTileCells = useMemo(
    () => tileSnapshot?.cells.filter((cell) => filteredRegionIds.has(cell.regionId)) ?? [],
    [filteredRegionIds, tileSnapshot]
  );
  const indexedRegions = useMemo(
    () =>
      [...filteredRegions]
        .sort((left, right) => right.riskScore - left.riskScore)
        .slice(0, 3),
    [filteredRegions]
  );
  const selectedRegion = regions.find((region) => region.id === selectedId) ?? null;
  useEffect(() => {
    if (!selectedId) return;
    if (!snapshot) return;
    if (regions.some((region) => region.id === selectedId)) return;
    setSelectedId(null);
    setDetailOpen(false);
  }, [regions, selectedId, snapshot]);
  const selectRegion = useCallback((id: string) => {
    setSelectedId(id);
    setDetailOpen(true);
    setFocusRequest({ regionId: id, nonce: Date.now() });
  }, []);

  return (
    <div className="flex min-h-full flex-col px-2 py-2 animate-fade-in sm:px-3 lg:px-4">
      <Card
        variant="flat"
        className="relative h-[calc(100vh-88px)] min-h-[560px] flex-1 overflow-hidden p-0 md:min-h-[620px]"
      >
        <div className="absolute left-3 right-3 top-3 z-40 grid gap-2 lg:left-4 lg:right-4 lg:top-4 xl:grid-cols-[minmax(260px,360px)_minmax(0,1fr)] xl:items-start">
          <div className="rounded-sm border border-white/[0.12] bg-black/38 px-3 py-2 shadow-data-panel backdrop-blur-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-text-primary">
                  <Globe2 className="h-4 w-4 text-brand-cyan" />
                  <h1 className="text-xl font-semibold leading-tight">{text("世界风险地图")}</h1>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-text-secondary">
                  {text("按商品属性自适应解释天气、物流、供应和价格传导")}
                </p>
              </div>
            </div>
            <StatusStrip snapshot={snapshot} lastUpdatedAt={lastUpdatedAt} />
          </div>

          <div className="grid min-w-0 gap-2 xl:justify-items-end">
            <div className="flex max-w-full flex-wrap items-center justify-end gap-1.5 rounded-sm border border-white/[0.12] bg-black/38 p-1.5 shadow-data-panel backdrop-blur-2xl">
              <WorldMapFilterDock
                filters={scopeFilters}
                options={snapshot?.filters ?? null}
                open={filtersOpen}
                onToggle={() => setFiltersOpen((value) => !value)}
                onChange={(nextFilters) => {
                  setScopeFilters(nextFilters);
                  setSelectedId(null);
                  setDetailOpen(false);
                }}
              />
              <span className="hidden h-7 items-center gap-1.5 rounded-xs border border-brand-emerald/20 bg-brand-emerald/10 px-2 text-caption text-brand-emerald-bright 2xl:inline-flex">
                <Layers3 className="h-3 w-3" />
                {text("活跃图层")} {snapshot?.layers.filter((layer) => layer.enabled).length ?? 0}
              </span>
              <RendererModeToggle value={rendererMode} onChange={setRendererMode} />
              <MapVisualLayerToggle
                layers={visibleLayers}
                onToggle={(layer) =>
                  setVisibleLayers((current) => ({
                    ...current,
                    [layer]: !current[layer],
                  }))
                }
              />
              <LiveUpdateBadge
                autoRefresh={autoRefresh}
                isRefreshing={isRefreshing}
                lastUpdatedAt={lastUpdatedAt}
              />
              {rendererMode === "webgl-ready" && (
                <TileRuntimeBadge runtime={tileRuntime} />
              )}
              <Button
                variant={autoRefresh ? "primary" : "secondary"}
                size="sm"
                onClick={() => setAutoRefresh((value) => !value)}
              >
                <Activity className="h-4 w-4" />
                {autoRefresh ? text("自动") : text("手动")}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => void loadSnapshot()} disabled={isRefreshing}>
                <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
                {text("刷新")}
              </Button>
            </div>
          </div>
        </div>

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_48%_38%,rgba(6,182,212,0.18),transparent_30%),radial-gradient(circle_at_80%_65%,rgba(16,185,129,0.13),transparent_24%),linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))]" />
        <div className="pointer-events-none absolute inset-0 z-10 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.45)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.45)_1px,transparent_1px)] [background-size:48px_48px]" />
        <WorldMapCanvas
          regions={filteredRegions}
          riskDeltas={riskDeltas}
          selectedId={selectedRegion?.id ?? null}
          tileCells={filteredTileCells}
          visibleLayers={visibleLayers}
          rendererMode={rendererMode}
          renderBudget={tileRuntime?.budget ?? "light"}
          focusRequest={focusRequest}
          onViewportChange={loadViewportTiles}
          onSelect={selectRegion}
        />

        <RiskRegionIndex
          regions={indexedRegions}
          selectedId={selectedRegion?.id ?? null}
          onSelect={selectRegion}
        />

        {source === "fallback" && (
          <div className="absolute inset-0 z-[70] flex items-center justify-center bg-black/65">
            <div className="rounded-sm border border-border-default bg-bg-surface px-5 py-4 text-sm text-text-secondary shadow-data-panel">
              {text("世界风险地图接口暂不可用")}
            </div>
          </div>
        )}
      </Card>

      {detailOpen && selectedRegion && (
        <RegionInsightModal
          region={selectedRegion}
          scopedEventId={scopedEventId}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </div>
  );
}

function EnhancedReadingPanel({
  regions,
  visibleLayers,
}: {
  regions: WorldMapRegion[];
  visibleLayers: VisibleMapLayers;
}) {
  const { lang, text } = useI18n();
  const topRegion = useMemo(
    () => [...regions].sort((left, right) => right.riskScore - left.riskScore)[0] ?? null,
    [regions]
  );
  const topBridge = useMemo(() => buildRiskBridges(regions)[0] ?? null, [regions]);
  const healthSummary = useMemo(() => summarizeEvidenceHealth(regions), [regions]);
  const linkedRegionCount = useMemo(
    () => regions.filter((region) => region.causalScope.hasDirectLinks).length,
    [regions]
  );
  const activeLayerLabels = MAP_VISUAL_LAYER_OPTIONS.filter((layer) => visibleLayers[layer.id]).map((layer) =>
    text(layer.label)
  );

  if (!topRegion) return null;

  const topColor = riskColor(topRegion.riskLevel);
  const topHealth = regionEvidenceHealth(topRegion);
  const topMomentum = regionRiskMomentum(topRegion);
  const topRegionName = lang === "zh" ? topRegion.nameZh : topRegion.nameEn;
  const topTrigger = lang === "zh" ? topRegion.story.triggerZh : topRegion.story.triggerEn;
  const bridgeLabel = topBridge
    ? `${lang === "zh" ? topBridge.source.nameZh : topBridge.source.nameEn} → ${
        lang === "zh" ? topBridge.target.nameZh : topBridge.target.nameEn
      }`
    : text("暂无传导");
  const bridgeDetail = topBridge
    ? topBridge.sharedSymbols.length > 0
      ? `${text("共享合约")} ${topBridge.sharedSymbols.slice(0, 3).join("/")}`
      : text("同商品")
    : text("当前筛选下暂无跨区飞线");

  return (
    <div
      data-testid="world-map-enhanced-reading-panel"
      className="pointer-events-none absolute bottom-4 right-[88px] z-20 hidden w-[300px] rounded-sm border border-brand-emerald/25 bg-black/66 p-2.5 shadow-data-panel backdrop-blur-xl xl:block"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <Sparkles className="h-4 w-4 text-brand-emerald-bright" />
            {text("增强阅读层")}
          </div>
          <p className="mt-0.5 text-caption leading-4 text-text-muted">
            {text("先读最高风险，再看跨区传导和证据密度")}
          </p>
        </div>
        <span className="rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-2 py-0.5 font-mono text-caption text-brand-emerald-bright">
          B.2.7
        </span>
      </div>

      <div className="mt-2 rounded-sm border border-border-subtle bg-black/36 p-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-caption text-text-muted">{text("主读区")}</span>
          <span className="font-mono text-sm" style={{ color: topColor.text }}>
            {topRegion.riskScore}
          </span>
        </div>
        <div className="mt-1 truncate text-sm font-semibold text-text-primary">{topRegionName}</div>
        <div className="mt-1 line-clamp-1 text-caption leading-4 text-text-secondary">{topTrigger}</div>
      </div>

      <div className="mt-2 grid gap-1.5">
        <ReadingMetric
          icon={Activity}
          label={text("风险动量")}
          value={text(momentumLabel(topMomentum.direction))}
          detail={`${topMomentum.delta > 0 ? "+" : ""}${topMomentum.delta} · ${
            lang === "zh" ? topMomentum.driverZh : topMomentum.driverEn
          }`}
        />
        <ReadingMetric
          icon={Route}
          label={text("跨区传导")}
          value={bridgeLabel}
          detail={bridgeDetail}
        />
        <ReadingMetric
          icon={DatabaseZap}
          label={text("证据密度")}
          value={`${topHealth.densityScore}/100`}
          detail={`${text("支持证据")} ${topHealth.evidenceCount} / ${text("反证")} ${topHealth.counterEvidenceCount}`}
        />
        <ReadingMetric
          icon={ShieldCheck}
          label={text("来源可信度")}
          value={`${healthSummary.sourceReliability}/100`}
          detail={`${text("来源数")} ${topHealth.runtimeSources} / ${text("新鲜来源")} ${topHealth.freshRuntimeSources}`}
        />
        <ReadingMetric
          icon={RefreshCw}
          label={text("数据新鲜度")}
          value={`${healthSummary.freshnessScore}/100`}
          detail={`${text("最高风险区域")}：${topRegionName}`}
        />
        <ReadingMetric
          icon={Link2}
          label={text("联动区域")}
          value={`${linkedRegionCount}/${regions.length}`}
          detail={`${text("活跃图层")}：${activeLayerLabels.length > 0 ? activeLayerLabels.join(" / ") : text("暂无")}`}
        />
      </div>
    </div>
  );
}

function summarizeEvidenceHealth(regions: WorldMapRegion[]) {
  if (regions.length === 0) {
    return { densityScore: 0, sourceReliability: 0, freshnessScore: 0 };
  }
  const healthRows = regions.map((region) => regionEvidenceHealth(region));
  return {
    densityScore: Math.round(healthRows.reduce((total, health) => total + health.densityScore, 0) / regions.length),
    sourceReliability: Math.round(
      healthRows.reduce((total, health) => total + health.sourceReliability, 0) / regions.length
    ),
    freshnessScore: Math.round(healthRows.reduce((total, health) => total + health.freshnessScore, 0) / regions.length),
  };
}

function regionEvidenceHealth(region: WorldMapRegion) {
  if (region.evidenceHealth) return region.evidenceHealth;

  const runtimeSourceCounts = [
    region.runtime.alerts,
    region.runtime.newsEvents,
    region.runtime.signals,
    region.runtime.positions,
    region.runtime.eventIntelligence ?? 0,
  ];
  const totalRuntimeRows = runtimeSourceCounts.reduce((total, count) => total + count, 0);
  const evidenceCount = region.story.evidence.length + region.adaptiveAlerts.length;
  const counterEvidenceCount = region.story.counterEvidence.length;
  const runtimeSources = runtimeSourceCounts.filter((count) => count > 0).length + (region.weather.dataSource ? 1 : 0);
  const eventFreshness = eventFreshnessScore(region.runtime.latestEventAt);
  const freshRuntimeSources =
    (region.weather.dataSource && region.weather.dataSource !== "regional_baseline_seed" ? 1 : 0) +
    (eventFreshness >= 70 ? runtimeSourceCounts.filter((count) => count > 0).length : 0);
  const densityScore = clamp(
    Math.round(evidenceCount * 9 + counterEvidenceCount * 7 + runtimeSources * 10 + Math.min(totalRuntimeRows, 12) * 3),
    0,
    100
  );
  const qualityComponent = region.eventQuality.total > 0 ? region.eventQuality.score : 55;
  const sourceReliability = clamp(
    Math.round(
      region.weather.confidence * 35 +
        qualityComponent * 0.35 +
        Math.min(runtimeSources / 4, 1) * 20 +
        Math.min((evidenceCount + counterEvidenceCount) / 7, 1) * 10
    ),
    0,
    100
  );
  const weatherFreshness =
    region.weather.dataSource !== "regional_baseline_seed" ? 72 : Math.round(region.weather.confidence * 60);
  const freshnessScore =
    totalRuntimeRows > 0
      ? Math.round(eventFreshness * 0.6 + weatherFreshness * 0.4)
      : weatherFreshness;

  return {
    evidenceCount,
    counterEvidenceCount,
    runtimeSources,
    freshRuntimeSources,
    sourceReliability,
    freshnessScore: clamp(freshnessScore, 0, 100),
    densityScore,
  };
}

function eventFreshnessScore(value: string | null) {
  if (!value) return 0;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return 0;
  const ageHours = Math.max((Date.now() - timestamp.getTime()) / 3_600_000, 0);
  if (ageHours <= 6) return 100;
  if (ageHours <= 24) return 86;
  if (ageHours <= 72) return 68;
  if (ageHours <= 168) return 48;
  return 25;
}

function regionRiskMomentum(region: WorldMapRegion): WorldMapRiskMomentum {
  if (region.riskMomentum) return region.riskMomentum;

  const health = regionEvidenceHealth(region);
  const runtimeRows =
    region.runtime.alerts +
    region.runtime.newsEvents +
    region.runtime.signals +
    region.runtime.positions +
    (region.runtime.eventIntelligence ?? 0);
  if ((region.runtime.eventIntelligence ?? 0) > 0 && region.eventQuality.blocked > region.eventQuality.passed) {
    const delta = -Math.min(18, 4 + region.eventQuality.blocked * 5 + region.eventQuality.review * 2);
    return {
      direction: "easing",
      delta,
      intensity: Math.min(Math.abs(delta) / 28, 1),
      driverZh: "质量门阻断",
      driverEn: "Quality gate blocked",
      reasonZh: "事件智能未通过质量门，地图保留阅读但不放大风险动量。",
      reasonEn: "Event intelligence failed the quality gate, so the map keeps it readable without amplifying momentum.",
      changedAt: region.runtime.latestEventAt,
    };
  }

  const weatherStress = Math.max(
    Math.abs(region.weather.precipitationAnomalyPct) / 55,
    region.weather.floodRisk,
    region.weather.droughtRisk
  );
  let delta =
    region.runtime.highSeverityAlerts * 7 +
    region.runtime.alerts * 3 +
    region.runtime.newsEvents * 2 +
    region.runtime.signals * 2 +
    region.runtime.positions +
    (region.runtime.eventIntelligence ?? 0) * 2 +
    region.eventQuality.passed * 4 +
    Math.round(region.weather.dataSource !== "regional_baseline_seed" ? weatherStress * 6 : 0) +
    Math.round(Math.max(health.freshnessScore - 65, 0) / 12);
  if (runtimeRows === 0 && region.weather.dataSource === "regional_baseline_seed") {
    delta = 0;
  }
  delta = clamp(delta, -100, 100);
  const direction: WorldMapRiskMomentumDirection = delta >= 5 ? "rising" : delta <= -5 ? "easing" : "steady";
  const primaryDriver = region.drivers[0];
  return {
    direction,
    delta,
    intensity: Math.min(Math.abs(delta) / 32, 1),
    driverZh: primaryDriver?.labelZh ?? "区域基线",
    driverEn: primaryDriver?.labelEn ?? "Regional baseline",
    reasonZh:
      direction === "rising"
        ? `${region.nameZh}风险升温：运行态信号、天气或事件智能证据正在增加。`
        : direction === "easing"
          ? `${region.nameZh}动量降温：缺少新鲜运行态证据或低质量事件被阻断。`
          : `${region.nameZh}暂无明显风险动量，当前主要作为基线观察。`,
    reasonEn:
      direction === "rising"
        ? `${region.nameEn} momentum is rising as runtime signals, weather, or event-intelligence evidence increases.`
        : direction === "easing"
          ? `${region.nameEn} momentum is easing because fresh runtime evidence is missing or weak events were blocked.`
          : `${region.nameEn} has no clear risk momentum and is mainly a baseline watch.`,
    changedAt: region.runtime.latestEventAt,
  };
}

function momentumLabel(direction: WorldMapRiskMomentumDirection) {
  if (direction === "rising") return "动量升温";
  if (direction === "easing") return "动量降温";
  return "动量稳定";
}

function momentumSymbol(direction: WorldMapRiskMomentumDirection) {
  if (direction === "rising") return "↑";
  if (direction === "easing") return "↓";
  return "→";
}

function momentumColor(direction: WorldMapRiskMomentumDirection) {
  if (direction === "rising") {
    return { text: "#ff4d4f", stroke: "rgba(255,77,79,0.78)", fill: "rgba(255,77,79,0.12)" };
  }
  if (direction === "easing") {
    return { text: "#10b981", stroke: "rgba(16,185,129,0.7)", fill: "rgba(16,185,129,0.1)" };
  }
  return { text: "#a3a3a3", stroke: "rgba(163,163,163,0.42)", fill: "rgba(163,163,163,0.08)" };
}

function regionRiskAction(region: WorldMapRegion) {
  const momentum = regionRiskMomentum(region);
  const health = regionEvidenceHealth(region);
  const hasQualityReview = region.eventQuality.blocked > 0 || region.eventQuality.review > 0;
  const needsEvidence = health.densityScore < 45 || health.sourceReliability < 45 || health.freshnessScore < 45;
  const eventIntelligenceHref = scopedWorldMapHref("/event-intelligence", region, { includeEvent: true });
  const newsHref = scopedWorldMapHref("/news", region);
  const causalWebHref = scopedWorldMapHref(region.causalScope.causalWebUrl, region, { includeEvent: true });

  if (hasQualityReview) {
    return {
      icon: ShieldAlert,
      color: "#f97316",
      title: "先复核质量门",
      description: "存在待复核或被阻断事件，先到事件智能确认质量，再追溯因果链。",
      primaryHref: eventIntelligenceHref,
      primaryLabel: "打开事件智能",
      primaryIcon: ShieldAlert,
      secondaryHref: causalWebHref,
      secondaryLabel: region.causalScope.hasDirectLinks ? "打开关联因果网络" : "打开同商品因果网络",
      secondaryIcon: Link2,
    };
  }

  if (needsEvidence) {
    return {
      icon: DatabaseZap,
      color: "#38bdf8",
      title: "先补证据",
      description: "当前证据覆盖偏薄，优先查看新闻、天气或信号来源，再进入链路追溯。",
      primaryHref: newsHref,
      primaryLabel: "打开新闻事件",
      primaryIcon: DatabaseZap,
      secondaryHref: causalWebHref,
      secondaryLabel: "打开因果网络",
      secondaryIcon: Link2,
    };
  }

  if (momentum.direction === "rising" && region.causalScope.hasDirectLinks) {
    return {
      icon: Activity,
      color: "#ff4d4f",
      title: "追溯升温链",
      description: "风险正在升温且存在直接事件作用域，优先进入因果网络核对上下游传导。",
      primaryHref: causalWebHref,
      primaryLabel: "打开关联因果网络",
      primaryIcon: Link2,
      secondaryHref: eventIntelligenceHref,
      secondaryLabel: "打开事件智能",
      secondaryIcon: ShieldCheck,
    };
  }

  if (region.causalScope.hasDirectLinks) {
    return {
      icon: Link2,
      color: "#22d3ee",
      title: "追溯因果链",
      description: "当前区域已有可追溯事件作用域，可进入因果网络核对上下游。",
      primaryHref: causalWebHref,
      primaryLabel: "打开关联因果网络",
      primaryIcon: Link2,
      secondaryHref: eventIntelligenceHref,
      secondaryLabel: "打开事件智能",
      secondaryIcon: ShieldCheck,
    };
  }

  return {
    icon: Compass,
    color: "#a3a3a3",
    title: "保持观察",
    description: "当前缺少直接事件作用域，先保持同商品观察，等待新鲜证据进入。",
    primaryHref: causalWebHref,
    primaryLabel: "打开同商品因果网络",
    primaryIcon: Link2,
    secondaryHref: newsHref,
    secondaryLabel: "打开新闻事件",
    secondaryIcon: DatabaseZap,
  };
}

function scopedWorldMapHref(
  href: string,
  region: WorldMapRegion,
  options: { includeEvent?: boolean } = {}
) {
  const event = options.includeEvent ? firstEventIntelligenceId(region) : undefined;
  return appendWorldMapNavigationScope(href, {
    symbol: region.causalScope.symbols[0] ?? region.symbols[0],
    region: region.id,
    ...(event ? { event } : {}),
  });
}

function firstEventIntelligenceId(region: WorldMapRegion) {
  const eventScope = region.causalScope.eventIds.find((eventId) =>
    eventId.startsWith("event_intelligence:")
  );
  return eventScope?.split(":")[1];
}

function ReadingMetric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-xs border border-border-subtle bg-black/28 px-2.5 py-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-caption text-text-muted">
          <Icon className="h-3.5 w-3.5 shrink-0 text-brand-cyan" />
          {label}
        </span>
      </div>
      <div className="mt-1 truncate text-xs font-semibold text-text-primary">{value}</div>
      <div className="mt-0.5 truncate text-[10px] text-text-muted">{detail}</div>
    </div>
  );
}

function TileRuntimeBadge({ runtime }: { runtime: TileRuntimeMetrics | null }) {
  const { text } = useI18n();

  if (!runtime) {
    return (
      <span className="inline-flex h-7 items-center gap-1.5 rounded-xs border border-border-subtle bg-black/28 px-2 text-caption text-text-muted">
        <DatabaseZap className="h-3 w-3 text-brand-cyan" />
        {text("瓦片准备中")}
      </span>
    );
  }

  return (
    <span
      title={`${text("天气瓦片")} ${runtime.weatherCells} / ${text("风险瓦片")} ${runtime.riskCells}`}
      className="inline-flex h-7 items-center gap-1.5 rounded-xs border border-brand-cyan/20 bg-brand-cyan/10 px-2 text-caption text-text-secondary"
    >
      <DatabaseZap className="h-3 w-3 text-brand-cyan" />
      <span>{text("瓦片")}</span>
      <span className="font-mono text-text-primary">{runtime.totalCells}</span>
      <span className="hidden text-text-disabled 2xl:inline">·</span>
      <span className="hidden font-mono text-brand-cyan 2xl:inline">{text(runtime.resolution)}</span>
      <span className="hidden text-text-disabled xl:inline">·</span>
      <span className={cn("hidden font-mono xl:inline", tileBudgetTone(runtime.budget))}>
        {text(tileBudgetLabel(runtime.budget))}
      </span>
      <span className="hidden text-text-disabled 2xl:inline">·</span>
      <span className="hidden font-mono text-text-muted 2xl:inline">
        {text("缓存")} {runtime.cacheEntries}
      </span>
      <span className="hidden text-text-disabled 2xl:inline">·</span>
      <span className="hidden font-mono text-text-muted 2xl:inline">
        {text(tileRuntimeStatusLabel(runtime.status))}
      </span>
      {runtime.budget !== "light" && (
        <>
          <span className="hidden text-text-disabled xl:inline">·</span>
          <span className="font-mono text-brand-orange">{text("已降载")}</span>
        </>
      )}
    </span>
  );
}

function StatusStrip({
  snapshot,
  lastUpdatedAt,
}: {
  snapshot: WorldMapSnapshot | null;
  lastUpdatedAt: Date | null;
}) {
  const { text } = useI18n();
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
      <StatusPill icon={Globe2} label={text("覆盖")} value={String(snapshot?.summary.regions ?? 0)} />
      <StatusPill
        icon={ShieldAlert}
        label={text("升温")}
        value={String(snapshot?.summary.elevatedRegions ?? 0)}
      />
      <StatusPill
        icon={Activity}
        label={text("最高")}
        value={String(snapshot?.summary.maxRiskScore ?? 0)}
      />
      <div className="flex min-w-0 items-center justify-between gap-2 rounded-xs border border-white/[0.10] bg-white/[0.04] px-2 py-1.5 backdrop-blur-xl">
        <span className="text-[10px] text-text-muted">{text("更新")}</span>
        <span className="font-mono text-xs text-text-primary">
          {lastUpdatedAt ? formatUpdateTime(lastUpdatedAt) : text("等待同步")}
        </span>
      </div>
    </div>
  );
}

function LiveUpdateBadge({
  autoRefresh,
  isRefreshing,
  lastUpdatedAt,
}: {
  autoRefresh: boolean;
  isRefreshing: boolean;
  lastUpdatedAt: Date | null;
}) {
  const { text } = useI18n();
  return (
    <div className="inline-flex h-7 items-center gap-2 rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-2 text-caption text-brand-emerald-bright backdrop-blur-xl">
      <span className={cn("h-1.5 w-1.5 rounded-full bg-brand-emerald-bright", autoRefresh && "animate-heartbeat")} />
      <span>{isRefreshing ? text("同步中") : autoRefresh ? text("轮询中") : text("手动刷新")}</span>
      {lastUpdatedAt && <span className="hidden font-mono text-text-muted 2xl:inline">{formatUpdateTime(lastUpdatedAt)}</span>}
    </div>
  );
}

function StatusPill({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-2 rounded-xs border border-white/[0.10] bg-white/[0.04] px-2 py-1.5 backdrop-blur-xl">
      <span className="flex min-w-0 items-center gap-1.5 truncate text-[10px] text-text-muted">
        <Icon className="h-3 w-3 shrink-0" />
        {label}
      </span>
      <span className="font-mono text-xs text-text-primary">{value}</span>
    </div>
  );
}

function WorldMapFilterDock({
  filters,
  onChange,
  onToggle,
  open,
  options,
}: {
  filters: WorldMapScopeFilters;
  onChange: (filters: WorldMapScopeFilters) => void;
  onToggle: () => void;
  open: boolean;
  options: WorldMapSnapshot["filters"] | null;
}) {
  const { lang, text } = useI18n();
  const summary = worldMapFilterSummary(filters, options, lang, text);

  return (
    <div className="relative">
      <button
        type="button"
        data-testid="world-map-filter-toggle"
        aria-expanded={open}
        onClick={onToggle}
        className={cn(
          "inline-flex h-7 max-w-[210px] items-center gap-1.5 rounded-xs border px-2 text-caption font-semibold transition-colors",
          open
            ? "border-brand-emerald/40 bg-brand-emerald/14 text-brand-emerald-bright"
            : "border-white/[0.10] bg-black/28 text-text-secondary hover:border-brand-emerald/30 hover:text-text-primary"
        )}
        title={`${text("筛选")} · ${summary}`}
      >
        <ListChecks className="h-3.5 w-3.5 shrink-0" />
        <span>{text("筛选")}</span>
        <span className="min-w-0 truncate font-mono text-[10px] text-text-muted">{summary}</span>
      </button>

      {open && (
        <div
          data-testid="world-map-filter-popover"
          className="absolute left-0 top-[calc(100%+8px)] z-50 w-[min(620px,calc(100vw-44px))] rounded-sm border border-white/[0.13] bg-black/62 p-2.5 shadow-data-panel backdrop-blur-2xl sm:left-auto sm:right-0 sm:w-[min(620px,calc(100vw-132px))]"
        >
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                <ListChecks className="h-4 w-4 text-brand-cyan" />
                {text("筛选")}
              </div>
              <div className="mt-0.5 max-w-[420px] truncate font-mono text-[10px] text-text-muted">
                {summary}
              </div>
            </div>
            <button
              type="button"
              className="flex h-7 w-7 items-center justify-center rounded-xs text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
              onClick={onToggle}
              aria-label={text("关闭")}
              title={text("关闭")}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <WorldMapScopeFilterPanel filters={filters} options={options} onChange={onChange} />
        </div>
      )}
    </div>
  );
}

function WorldMapScopeFilterPanel({
  filters,
  options,
  onChange,
}: {
  filters: WorldMapScopeFilters;
  options: WorldMapSnapshot["filters"] | null;
  onChange: (filters: WorldMapScopeFilters) => void;
}) {
  const { text, lang } = useI18n();
  const sourceOptions = options?.sources ?? [];
  const mechanismOptions = options?.mechanisms ?? [];
  const symbolOptions = options?.symbols ?? [];
  const update = (key: keyof WorldMapScopeFilters, value: ScopeFilterValue) => {
    onChange({ ...filters, [key]: value });
  };

  return (
    <div className="grid gap-1.5">
      <ScopeFilterRow
        label={text("事件源")}
        value={filters.source}
        options={sourceOptions}
        onChange={(value) => update("source", value)}
        optionLabel={(option) => (lang === "zh" ? option.labelZh : option.labelEn)}
      />
      <ScopeFilterRow
        label={text("品种")}
        value={filters.symbol}
        options={symbolOptions.map((symbol) => ({ id: symbol, labelZh: symbol, labelEn: symbol }))}
        onChange={(value) => update("symbol", value)}
        optionLabel={(option) => option.id}
      />
      <ScopeFilterRow
        label={text("机制")}
        value={filters.mechanism}
        options={mechanismOptions}
        onChange={(value) => update("mechanism", value)}
        optionLabel={(option) => (lang === "zh" ? option.labelZh : option.labelEn)}
      />
    </div>
  );
}

function ScopeFilterRow({
  label,
  value,
  options,
  onChange,
  optionLabel,
}: {
  label: string;
  value: ScopeFilterValue;
  options: WorldMapFilterOption[];
  onChange: (value: ScopeFilterValue) => void;
  optionLabel: (option: WorldMapFilterOption) => string;
}) {
  const { text } = useI18n();
  const allOption: WorldMapFilterOption = { id: "all", labelZh: "全部", labelEn: "All" };
  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] items-center gap-1.5">
      <span className="text-[10px] font-semibold text-text-muted">{label}</span>
      <div className="flex max-w-full gap-1 overflow-x-auto">
        {[allOption, ...options.filter((option) => option.id !== "all")].map((option) => {
          const active = value === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onChange(option.id)}
              className={cn(
                "h-7 shrink-0 rounded-xs border px-2 text-[11px] font-semibold transition-colors",
                active
                  ? "border-brand-emerald/40 bg-brand-emerald text-black"
                  : "border-transparent text-text-muted hover:bg-bg-surface-raised hover:text-text-primary"
              )}
              title={option.id === "all" ? text("全部") : optionLabel(option)}
            >
              {option.id === "all" ? text("全部") : optionLabel(option)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function worldMapFilterSummary(
  filters: WorldMapScopeFilters,
  options: WorldMapSnapshot["filters"] | null,
  lang: "zh" | "en",
  text: (source: string) => string
): string {
  const activeParts = [
    filters.source !== "all"
      ? worldMapFilterOptionLabel(filters.source, options?.sources ?? [], lang)
      : null,
    filters.symbol !== "all" ? filters.symbol : null,
    filters.mechanism !== "all"
      ? worldMapFilterOptionLabel(filters.mechanism, options?.mechanisms ?? [], lang)
      : null,
  ].filter(Boolean);

  return activeParts.length > 0 ? activeParts.join(" / ") : text("全部");
}

function worldMapFilterOptionLabel(
  value: ScopeFilterValue,
  options: WorldMapFilterOption[],
  lang: "zh" | "en"
): string {
  const option = options.find((item) => item.id === value);
  if (!option) return value;
  return lang === "zh" ? option.labelZh : option.labelEn;
}

function LayerLegend({ layers }: { layers: WorldMapLayer[] }) {
  const { lang, text } = useI18n();
  return (
    <div className="hidden flex-wrap items-center gap-1.5 lg:flex">
      {layers.slice(0, 4).map((layer) => (
        <span
          key={layer.id}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-xs border px-2 text-caption",
            layer.status === "ready" && "border-brand-emerald/25 text-brand-emerald-bright",
            layer.status === "baseline" && "border-brand-cyan/25 text-brand-cyan",
            layer.status === "planned" && "border-border-subtle text-text-muted"
          )}
        >
          <Layers3 className="h-3 w-3" />
          {lang === "zh" ? layer.labelZh : layer.labelEn}
        </span>
      ))}
      {layers.length === 0 && <span className="text-caption text-text-muted">{text("图层等待同步")}</span>}
    </div>
  );
}

function MapVisualLayerToggle({
  layers,
  onToggle,
}: {
  layers: VisibleMapLayers;
  onToggle: (layer: WorldMapVisualLayer) => void;
}) {
  const { text } = useI18n();
  return (
    <div
      data-testid="world-map-layer-toggle"
      className="flex max-w-full items-center gap-1 overflow-x-auto rounded-xs border border-white/[0.08] bg-black/30 p-0.5"
      aria-label={text("视觉图层")}
    >
      {MAP_VISUAL_LAYER_OPTIONS.map(({ id, label, icon: Icon }) => {
        const active = layers[id];
        return (
          <button
            key={id}
            type="button"
            data-testid={`world-map-layer-toggle-${id}`}
            aria-pressed={active}
            onClick={() => onToggle(id)}
            className={cn(
              "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-xs border px-2 text-caption font-semibold transition-colors",
              active
                ? "border-brand-cyan/35 bg-brand-cyan/12 text-brand-cyan"
                : "border-transparent text-text-muted hover:bg-white/[0.05] hover:text-text-primary"
            )}
            title={text(label)}
          >
            <Icon className="h-3 w-3" />
            <span className="hidden 2xl:inline">{text(label)}</span>
          </button>
        );
      })}
    </div>
  );
}

function RendererModeToggle({
  value,
  onChange,
}: {
  value: WorldMapRendererMode;
  onChange: (value: WorldMapRendererMode) => void;
}) {
  const { text } = useI18n();
  return (
    <div
      data-testid="world-map-renderer-toggle"
      className="flex max-w-full items-center gap-1 overflow-x-auto rounded-xs border border-white/[0.08] bg-black/30 p-0.5"
      aria-label={text("渲染模式")}
    >
      {MAP_RENDERER_OPTIONS.map((option) => {
        const active = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            data-testid={`world-map-renderer-toggle-${option.id}`}
            aria-pressed={active}
            onClick={() => onChange(option.id)}
            className={cn(
              "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-xs border px-2 text-caption font-semibold transition-colors",
              active
                ? "border-brand-emerald/35 bg-brand-emerald/12 text-brand-emerald-bright"
                : "border-transparent text-text-muted hover:bg-white/[0.05] hover:text-text-primary"
            )}
            title={text(option.detail)}
          >
            <Sparkles className="h-3 w-3" />
            <span className="hidden sm:inline">{text(option.label)}</span>
          </button>
        );
      })}
    </div>
  );
}

function RiskRegionIndex({
  regions,
  selectedId,
  onSelect,
}: {
  regions: WorldMapRegion[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { lang, text } = useI18n();
  return (
    <div
      data-testid="world-map-region-index"
      className="absolute bottom-4 left-4 z-30 w-[min(360px,calc(100%-112px))] rounded-sm border border-white/[0.12] bg-black/42 shadow-data-panel backdrop-blur-2xl"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border-subtle px-3 py-2">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <Compass className="h-4 w-4 text-brand-cyan" />
            {text("高风险索引")}
          </div>
          <p className="mt-0.5 text-caption text-text-muted">{text("按当前筛选排序")}</p>
        </div>
        <span className="rounded-xs border border-brand-cyan/25 bg-brand-cyan/10 px-2 py-0.5 font-mono text-caption text-brand-cyan">
          {regions.length}
        </span>
      </div>
      <div className="grid max-h-[178px] gap-1 overflow-y-auto p-2">
        {regions.length === 0 && (
          <div className="col-span-full rounded-xs border border-border-subtle bg-black/28 px-3 py-2 text-caption text-text-muted">
            {text("暂无区域")}
          </div>
        )}
        {regions.map((region, index) => {
          const active = region.id === selectedId;
          const color = riskColor(region.riskLevel);
          const momentum = regionRiskMomentum(region);
          const momentumTone = momentumColor(momentum.direction);
          return (
            <button
              key={region.id}
              type="button"
              data-testid={`world-map-region-index-item-${region.id}`}
              onClick={() => onSelect(region.id)}
              className={cn(
                "group min-w-0 rounded-xs border bg-black/24 px-2.5 py-2 text-left backdrop-blur-xl transition-colors",
                active
                  ? "border-brand-cyan/45 bg-brand-cyan/12"
                  : "border-border-subtle hover:border-brand-cyan/25 hover:bg-white/[0.045]"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="font-mono text-[10px] text-text-muted">#{index + 1}</span>
                  <span className="truncate text-xs font-semibold text-text-primary">
                    {lang === "zh" ? region.nameZh : region.nameEn}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {momentum.direction !== "steady" && (
                    <span className="font-mono text-[10px]" style={{ color: momentumTone.text }}>
                      {momentumSymbol(momentum.direction)}
                      {momentum.delta > 0 ? "+" : ""}
                      {momentum.delta}
                    </span>
                  )}
                  <span className="font-mono text-xs" style={{ color: color.text }}>
                    {region.riskScore}
                  </span>
                </span>
              </div>
              <div className="mt-1 truncate text-[10px] text-text-muted">
                {text(momentumLabel(momentum.direction))} · {(lang === "zh" ? region.story.triggerZh : region.story.triggerEn)} · {region.symbols.join("/")}
              </div>
            </button>
          );
        })}
      </div>
      <div className="border-t border-border-subtle px-3 py-1.5 text-caption text-text-muted">
        {text("点击区域查看动态风险链")}
      </div>
    </div>
  );
}

function WorldMapCanvas({
  regions,
  riskDeltas,
  selectedId,
  tileCells,
  visibleLayers,
  rendererMode,
  renderBudget,
  focusRequest,
  onViewportChange,
  onSelect,
}: {
  regions: WorldMapRegion[];
  riskDeltas: Record<string, number>;
  selectedId: string | null;
  tileCells: WorldMapTileCell[];
  visibleLayers: VisibleMapLayers;
  rendererMode: WorldMapRendererMode;
  renderBudget: TileRuntimeBudget;
  focusRequest: MapFocusRequest | null;
  onViewportChange: (viewport: WorldMapViewport, scale: number) => void;
  onSelect: (id: string) => void;
}) {
  const { lang } = useI18n();
  const [view, setView] = useState<MapViewTransform>(INITIAL_MAP_VIEW);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startView: MapViewTransform;
  } | null>(null);
  const [dragging, setDragging] = useState(false);
  const projection = useMemo(
    () =>
      geoEqualEarth().fitExtent(
        [
          [30, 72],
          [MAP_WIDTH - 30, MAP_HEIGHT - 24],
        ],
        WORLD_COUNTRIES as GeoPermissibleObjects
      ),
    []
  );
  const path = useMemo(() => geoPath(projection), [projection]);
  const countryPaths = useMemo(
    () =>
      WORLD_COUNTRIES.features
        .map((country, index) => ({
          id: String(country.id ?? index),
          d: path(country as GeoPermissibleObjects) ?? "",
        }))
        .filter((country) => country.d.length > 0),
    [path]
  );
  const graticulePath = useMemo(() => path(WORLD_GRATICULE as GeoPermissibleObjects) ?? "", [path]);
  const borderPath = useMemo(() => path(WORLD_BORDERS as GeoPermissibleObjects) ?? "", [path]);
  const renderBudgetSpec = WORLD_MAP_TILE_RENDER_BUDGETS[renderBudget];
  const riskRoutes = useMemo(
    () => buildRiskRoutes(regions, renderBudgetSpec.routes),
    [regions, renderBudgetSpec.routes]
  );
  const densityCells = useMemo(
    () => buildRiskDensityCells(regions, projection, tileCells, renderBudgetSpec.densityCells),
    [projection, regions, renderBudgetSpec.densityCells, tileCells]
  );
  const weatherTileCells = useMemo(
    () => buildWeatherTileCells(regions, projection, tileCells, renderBudgetSpec.weatherCells),
    [projection, regions, renderBudgetSpec.weatherCells, tileCells]
  );
  const regionLabels = useMemo(
    () =>
      buildRegionMapLabels({
        projection,
        regions,
        renderBudget,
        riskDeltas,
        selectedId,
        view,
      }),
    [projection, regions, renderBudget, riskDeltas, selectedId, view]
  );
  const regionLabelsById = useMemo(
    () => new Map(regionLabels.map((label) => [label.id, label])),
    [regionLabels]
  );
  const viewport = useMemo(() => computeMapViewport(view, projection), [projection, view]);

  useEffect(() => {
    onViewportChange(viewport, view.scale);
  }, [
    onViewportChange,
    view.scale,
    viewport.maxLat,
    viewport.maxLon,
    viewport.minLat,
    viewport.minLon,
  ]);

  useEffect(() => {
    if (!focusRequest) return;
    const region = regions.find((item) => item.id === focusRequest.regionId);
    if (!region) return;
    const center = project(region.center, projection);
    const scale = 1.42;
    setView(
      clampMapView({
        scale,
        x: MAP_WIDTH / 2 - center.x * scale,
        y: MAP_HEIGHT / 2 - center.y * scale,
      })
    );
  }, [focusRequest, projection, regions]);

  const applyZoom = useCallback((factor: number, anchor = { x: MAP_WIDTH / 2, y: MAP_HEIGHT / 2 }) => {
    setView((current) => {
      const nextScale = clamp(current.scale * factor, MIN_MAP_SCALE, MAX_MAP_SCALE);
      const ratio = nextScale / current.scale;
      return clampMapView({
        scale: nextScale,
        x: anchor.x - (anchor.x - current.x) * ratio,
        y: anchor.y - (anchor.y - current.y) * ratio,
      });
    });
  }, []);

  const handleWheel = useCallback((event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const anchor = {
      x: ((event.clientX - bounds.left) / bounds.width) * MAP_WIDTH,
      y: ((event.clientY - bounds.top) / bounds.height) * MAP_HEIGHT,
    };
    applyZoom(event.deltaY < 0 ? 1.16 : 0.86, anchor);
  }, [applyZoom]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    const target = event.target;
    if (target instanceof Element && target.closest("[data-region-node='true']")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startView: view,
    };
    setDragging(true);
  }, [view]);

  const handlePointerMove = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    const dragState = dragRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const dx = ((event.clientX - dragState.startX) / bounds.width) * MAP_WIDTH;
    const dy = ((event.clientY - dragState.startY) / bounds.height) * MAP_HEIGHT;
    setView(
      clampMapView({
        scale: dragState.startView.scale,
        x: dragState.startView.x + dx,
        y: dragState.startView.y + dy,
      })
    );
  }, []);

  const handlePointerEnd = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      setDragging(false);
    }
  }, []);

  return (
    <div className="absolute inset-0">
      <svg
        className={cn("relative z-10 h-full w-full touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")}
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        role="img"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
      >
        <defs>
          <radialGradient id="worldMapOceanGlow" cx="50%" cy="45%" r="62%">
            <stop offset="0%" stopColor="rgba(8,145,178,0.22)" />
            <stop offset="58%" stopColor="rgba(6,95,70,0.08)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </radialGradient>
          <linearGradient id="worldMapCountryFill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(15,23,42,0.68)" />
            <stop offset="55%" stopColor="rgba(10,18,24,0.58)" />
            <stop offset="100%" stopColor="rgba(4,10,8,0.62)" />
          </linearGradient>
          <linearGradient id="worldMapRouteLine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(34,211,238,0.06)" />
            <stop offset="48%" stopColor="rgba(16,185,129,0.55)" />
            <stop offset="100%" stopColor="rgba(249,115,22,0.5)" />
          </linearGradient>
          <filter id="worldMapRiskGlow">
            <feGaussianBlur stdDeviation="10" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="worldMapLandGlow">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect x="0" y="0" width={MAP_WIDTH} height={MAP_HEIGHT} fill="url(#worldMapOceanGlow)" />
        <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
          {rendererMode === "webgl-ready" && (
            <foreignObject
              x="0"
              y="0"
              width={MAP_WIDTH}
              height={MAP_HEIGHT}
              className="pointer-events-none"
            >
              <div className="relative h-full w-full overflow-hidden opacity-70 mix-blend-screen">
                <MapLibreBasemapPreview regions={regions} showRiskRegions={visibleLayers.heat} />
                <WorldMapWebGlPreview
                  densityCells={densityCells}
                  projection={projection}
                  regions={regions}
                  routes={riskRoutes}
                  visibleLayers={visibleLayers}
                  weatherTileCells={weatherTileCells}
                />
              </div>
            </foreignObject>
          )}
          <path
            d={graticulePath}
            fill="none"
            stroke="rgba(148,163,184,0.12)"
            strokeWidth="0.7"
            strokeDasharray="2 9"
            vectorEffect="non-scaling-stroke"
          />
          <g filter="url(#worldMapLandGlow)" opacity="0.96">
            {countryPaths.map((country) => (
              <path
                key={country.id}
                data-map-layer="country"
                d={country.d}
                fill="url(#worldMapCountryFill)"
                stroke="rgba(34,211,238,0.08)"
                strokeWidth="0.45"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </g>
          <path
            d={borderPath}
            fill="none"
            stroke="rgba(148,163,184,0.14)"
            strokeWidth="0.55"
            vectorEffect="non-scaling-stroke"
          />

          {visibleLayers.density && (
            <g data-testid="world-map-density-layer" data-map-layer="density">
              {densityCells.map((cell) => {
                const color = riskColor(cell.riskLevel);
                return (
                  <rect
                    key={cell.id}
                    data-region-id={cell.regionId}
                    x={cell.x - cell.size / 2}
                    y={cell.y - cell.size / 2}
                    width={cell.size}
                    height={cell.size}
                    rx={cell.size * 0.18}
                    fill={color.strokeStrong}
                    opacity={0.05 + cell.intensity * 0.32}
                    vectorEffect="non-scaling-stroke"
                  />
                );
              })}
            </g>
          )}

          {visibleLayers.weather &&
            regions.map((region) => {
              const center = project(region.center, projection);
              const anomaly = region.weather.precipitationAnomalyPct;
              const radius = clamp(28 + region.weather.floodRisk * 58 + Math.abs(anomaly) * 0.7, 34, 116);
              const weatherColor =
                anomaly >= 0 ? "rgba(34,211,238,0.24)" : "rgba(249,115,22,0.2)";
              const weatherStroke =
                anomaly >= 0 ? "rgba(34,211,238,0.42)" : "rgba(249,115,22,0.38)";
              return (
                <g key={`${region.id}-weather`} data-map-layer="weather">
                  <circle
                    cx={center.x}
                    cy={center.y}
                    r={radius}
                    fill={weatherColor}
                    stroke={weatherStroke}
                    strokeWidth="1"
                    opacity={0.18 + Math.min(0.38, region.weather.floodRisk * 0.38)}
                    vectorEffect="non-scaling-stroke"
                  />
                  <circle
                    cx={center.x}
                    cy={center.y}
                    r={Math.max(16, radius * 0.44)}
                    fill="none"
                    stroke={weatherStroke}
                    strokeWidth="1"
                    strokeDasharray="2 7"
                    opacity="0.45"
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}

          {visibleLayers.routes && riskRoutes.map((route) => {
            const d = arcPath(route.from, route.to, projection);
            if (!d) return null;
            return (
              <path
                key={route.id}
                className="world-map-route-flow"
                d={d}
                fill="none"
                stroke="url(#worldMapRouteLine)"
                strokeWidth={1 + route.weight * 2.4}
                strokeDasharray="8 10"
                opacity={0.22 + route.weight * 0.34}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}

          {regions.map((region) => {
            const center = project(region.center, projection);
            const selected = region.id === selectedId;
            const label = regionLabelsById.get(region.id);
            const color = riskColor(region.riskLevel);
            const radius = 22 + region.riskScore * 0.42;
            const delta = riskDeltas[region.id] ?? 0;
            const momentum = regionRiskMomentum(region);
            const momentumTone = momentumColor(momentum.direction);
            const heatVisible = visibleLayers.heat;
            return (
              <g
                key={region.id}
                role="button"
                tabIndex={0}
                data-region-node="true"
                className="cursor-pointer outline-none"
                onClick={() => onSelect(region.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelect(region.id);
                }}
              >
                <path
                  d={polygonPath(region.polygon, projection)}
                  fill={heatVisible ? color.fill : "rgba(0,0,0,0.05)"}
                  stroke={selected ? color.strokeStrong : heatVisible ? color.stroke : "rgba(148,163,184,0.2)"}
                  strokeWidth={selected ? 2.8 : heatVisible ? 1.2 : 0.85}
                  filter={selected && heatVisible ? "url(#worldMapRiskGlow)" : undefined}
                  vectorEffect="non-scaling-stroke"
                />
                {heatVisible && momentum.direction !== "steady" && momentum.intensity > 0 && (
                  <circle
                    cx={center.x}
                    cy={center.y}
                    r={radius * 0.58}
                    fill={momentumTone.fill}
                    stroke={momentumTone.stroke}
                    strokeWidth={1 + momentum.intensity * 2.4}
                    opacity={0.22 + momentum.intensity * 0.3}
                    vectorEffect="non-scaling-stroke"
                  >
                    <animate
                      attributeName="r"
                      values={`${radius * 0.55};${radius + 18 + momentum.intensity * 18};${radius * 0.55}`}
                      dur={momentum.direction === "rising" ? "2.15s" : "3.2s"}
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values={`${0.24 + momentum.intensity * 0.32};0.05;${0.24 + momentum.intensity * 0.32}`}
                      dur={momentum.direction === "rising" ? "2.15s" : "3.2s"}
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                {heatVisible && (
                  <circle
                    cx={center.x}
                    cy={center.y}
                    r={radius}
                    fill="none"
                    stroke={color.stroke}
                    strokeWidth="1.5"
                    strokeDasharray="3 8"
                    opacity={selected ? 0.88 : 0.38}
                    vectorEffect="non-scaling-stroke"
                  >
                    <animate
                      attributeName="r"
                      values={`${radius};${radius + 12};${radius}`}
                      dur={selected ? "2.2s" : "3.4s"}
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                {heatVisible && delta !== 0 && (
                  <circle
                    key={`${region.id}-${delta}`}
                    cx={center.x}
                    cy={center.y}
                    r="10"
                    fill="none"
                    stroke={delta > 0 ? "#ff4d4f" : "#10b981"}
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                  >
                    <animate attributeName="r" values="10;68" dur="1.25s" repeatCount="1" />
                    <animate attributeName="opacity" values="0.8;0" dur="1.25s" repeatCount="1" />
                  </circle>
                )}
                <circle cx={center.x} cy={center.y} r={7} fill={color.strokeStrong} filter="url(#worldMapRiskGlow)" />
                <circle cx={center.x} cy={center.y} r={2.8} fill="#fff" opacity="0.72" />
                {visibleLayers.labels && label && (
                  <>
                    <line
                      x1={center.x}
                      y1={center.y}
                      x2={label.anchorX}
                      y2={label.anchorY}
                      stroke={selected ? color.strokeStrong : "rgba(148,163,184,0.28)"}
                      strokeWidth={selected ? 1.25 : 0.8}
                      strokeDasharray="2 4"
                      opacity={selected ? 0.68 : 0.36}
                      vectorEffect="non-scaling-stroke"
                    />
                    <g
                      data-testid="world-map-region-label"
                      transform={`translate(${label.x} ${label.y}) scale(${1 / view.scale})`}
                    >
                      <foreignObject width={label.width} height={label.height}>
                        <div
                          className={cn(
                            "h-full rounded-sm border px-2 py-1 shadow-data-panel backdrop-blur-2xl",
                            selected
                              ? "border-brand-cyan/50 bg-brand-cyan/12"
                              : "border-white/[0.12] bg-black/56"
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="truncate text-[11px] font-semibold text-text-primary">
                              {lang === "zh" ? region.nameZh : region.nameEn}
                            </div>
                            <div className="font-mono text-[11px]" style={{ color: color.text }}>
                              {region.riskScore}
                            </div>
                          </div>
                          <div className="mt-0.5 flex items-center gap-1 truncate text-[10px] text-text-muted">
                            {region.symbols.join("/")}
                            {momentum.direction !== "steady" && (
                              <span className="font-mono" style={{ color: momentumTone.text }}>
                                {momentumSymbol(momentum.direction)}
                                {momentum.delta > 0 ? "+" : ""}
                                {momentum.delta}
                              </span>
                            )}
                            {delta !== 0 && (
                              <span className={cn("font-mono", delta > 0 ? "text-data-down" : "text-data-up")}>
                                {delta > 0 ? "+" : ""}
                                {delta}
                              </span>
                            )}
                          </div>
                        </div>
                      </foreignObject>
                    </g>
                  </>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      <MapZoomControls
        scale={view.scale}
        onZoomIn={() => applyZoom(1.22)}
        onZoomOut={() => applyZoom(0.82)}
        onReset={() => setView(INITIAL_MAP_VIEW)}
      />
    </div>
  );
}

function MapLibreBasemapPreview({
  regions,
  showRiskRegions,
}: {
  regions: WorldMapRegion[];
  showRiskRegions: boolean;
}) {
  const { text } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [status, setStatus] = useState<MapLibreRuntimeStatus>("loading");
  const regionCollection = useMemo(() => buildMapLibreRegionCollection(regions), [regions]);

  useEffect(() => {
    let cancelled = false;

    async function mountMap() {
      try {
        const maplibre = await import("maplibre-gl");
        if (cancelled || !containerRef.current) return;

        const map = new maplibre.Map({
          attributionControl: false,
          center: [18, 10],
          container: containerRef.current,
          fadeDuration: 0,
          interactive: false,
          pitch: 0,
          style: buildMapLibreStyle(regionCollection, showRiskRegions),
          zoom: 0.45,
        });

        mapRef.current = map;
        map.once("load", () => {
          if (!cancelled) setStatus("ready");
        });
        map.on("error", () => {
          if (!cancelled) setStatus("error");
        });
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    void mountMap();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const source = map.getSource("risk-regions") as GeoJSONSource | undefined;
    source?.setData(regionCollection);
  }, [regionCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    setMapLibreLayerVisibility(map, ["risk-region-fill", "risk-region-line"], showRiskRegions);
  }, [showRiskRegions]);

  return (
    <div
      data-testid="world-map-maplibre-basemap"
      className="pointer-events-none absolute inset-0 z-[1] overflow-hidden opacity-40 mix-blend-screen"
      aria-hidden="true"
    >
      <div ref={containerRef} className="h-full w-full [&_.maplibregl-canvas]:!h-full [&_.maplibregl-canvas]:!w-full" />
      <div
        data-testid={`world-map-maplibre-status-${status}`}
        className="absolute left-4 top-[118px] rounded-xs border border-brand-emerald/20 bg-black/58 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-brand-emerald-bright"
      >
        {text(status === "ready" ? "MapLibre已就绪" : status === "error" ? "MapLibre异常" : "MapLibre加载中")}
      </div>
    </div>
  );
}

function WorldMapWebGlPreview({
  densityCells,
  projection,
  regions,
  routes,
  visibleLayers,
  weatherTileCells,
}: {
  densityCells: RiskDensityCell[];
  projection: GeoProjection;
  regions: WorldMapRegion[];
  routes: RiskRoute[];
  visibleLayers: VisibleMapLayers;
  weatherTileCells: WeatherTileCell[];
}) {
  const regionPolygons = useMemo<WebGlRegionPolygon[]>(
    () =>
      regions.map((region) => {
        const color = riskColor(region.riskLevel);
        return {
          id: region.id,
          polygon: region.polygon.map((point) => {
            const projected = project(point, projection);
            return [projected.x, projected.y, 0];
          }),
          fillColor: colorToRgba(color.strokeStrong, 32),
          lineColor: colorToRgba(color.strokeStrong, 110),
        };
      }),
    [projection, regions]
  );
  const projectedRoutes = useMemo<WebGlRoute[]>(
    () =>
      routes.map((route) => {
        const from = project(route.from, projection);
        const to = project(route.to, projection);
        return {
          id: route.id,
          from: [from.x, from.y, 0],
          to: [to.x, to.y, 0],
          weight: route.weight,
        };
      }),
    [projection, routes]
  );
  const layers = useMemo(() => {
    const nextLayers = [];

    if (visibleLayers.weather) {
      nextLayers.push(
        new PolygonLayer<WeatherTileCell>({
          id: "world-map-webgl-weather-tiles",
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          data: weatherTileCells,
          filled: true,
          getFillColor: (item) => item.fillColor,
          getLineColor: (item) => item.lineColor,
          getLineWidth: 0.5,
          getPolygon: (item) => item.polygon,
          lineWidthUnits: "pixels",
          pickable: false,
          stroked: true,
        })
      );
    }

    if (visibleLayers.heat) {
      nextLayers.push(
        new PolygonLayer<WebGlRegionPolygon>({
          id: "world-map-webgl-polygons",
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          data: regionPolygons,
          filled: true,
          getFillColor: (item) => item.fillColor,
          getLineColor: (item) => item.lineColor,
          getLineWidth: 1,
          getPolygon: (item) => item.polygon,
          lineWidthUnits: "pixels",
          pickable: false,
          stroked: true,
        })
      );
    }

    if (visibleLayers.density) {
      nextLayers.push(
        new ScatterplotLayer<RiskDensityCell>({
          id: "world-map-webgl-density",
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          data: densityCells,
          getFillColor: (cell) => colorToRgba(riskColor(cell.riskLevel).strokeStrong, 42 + cell.intensity * 96),
          getLineColor: (cell) => colorToRgba(riskColor(cell.riskLevel).strokeStrong, 78),
          getLineWidth: 0.7,
          getPosition: (cell) => [cell.x, cell.y, 0],
          getRadius: (cell) => cell.size * (0.74 + cell.intensity * 0.56),
          lineWidthUnits: "pixels",
          pickable: false,
          radiusUnits: "pixels",
          stroked: true,
        })
      );
    }

    if (visibleLayers.routes) {
      nextLayers.push(
        new ArcLayer<WebGlRoute>({
          id: "world-map-webgl-arcs",
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          data: projectedRoutes,
          getSourceColor: [34, 211, 238, 92],
          getSourcePosition: (route) => route.from,
          getTargetColor: [249, 115, 22, 132],
          getTargetPosition: (route) => route.to,
          getWidth: (route) => 1 + route.weight * 2,
          pickable: false,
          widthUnits: "pixels",
        })
      );
    }

    return nextLayers;
  }, [
    densityCells,
    projectedRoutes,
    regionPolygons,
    visibleLayers.density,
    visibleLayers.heat,
    visibleLayers.routes,
    visibleLayers.weather,
    weatherTileCells,
  ]);

  return (
    <div
      data-testid="world-map-webgl-preview"
      className="pointer-events-none absolute inset-0 z-[2] opacity-70 mix-blend-screen"
      aria-hidden="true"
    >
      <DeckGL
        controller={false}
        initialViewState={{ target: [MAP_WIDTH / 2, MAP_HEIGHT / 2, 0], zoom: 0 }}
        layers={layers}
        style={{ pointerEvents: "none" }}
        views={new OrthographicView({ id: "world-map-webgl-view", flipY: false })}
      />
    </div>
  );
}

function WebGlReadinessPanel({
  activeEnhancedLayerCount,
  densityCellCount,
  regionCount,
  routeCount,
  weatherTileCount,
}: {
  activeEnhancedLayerCount: number;
  densityCellCount: number;
  regionCount: number;
  routeCount: number;
  weatherTileCount: number;
}) {
  const { text } = useI18n();
  const rows = [
    { label: "MapLibre底图", value: text("离线运行"), status: "ready" },
    { label: "视图同步", value: text("已同步"), status: "ready" },
    { label: "图层联动", value: `${activeEnhancedLayerCount}/4`, status: "ready" },
    { label: "GeoJson区域", value: regionCount, status: "ready" },
    { label: "Heatmap密度", value: densityCellCount, status: "ready" },
    { label: "Arc飞线", value: routeCount, status: "ready" },
    { label: "Tile天气", value: weatherTileCount, status: "ready" },
  ];
  return (
    <div
      data-testid="world-map-webgl-readiness"
      className="pointer-events-none absolute right-4 top-[132px] z-20 hidden w-[210px] rounded-sm border border-brand-emerald/25 bg-black/58 p-2.5 shadow-data-panel backdrop-blur-xl xl:block"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <Sparkles className="h-4 w-4 text-brand-emerald-bright" />
            {text("WebGL 预备")}
          </div>
          <p className="mt-0.5 text-caption leading-4 text-text-muted">
            {text("GPU 图层按 deck.gl 口径组织")}
          </p>
        </div>
        <span className="rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-2 py-0.5 font-mono text-caption text-brand-emerald-bright">
          B.2
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1">
        {rows.slice(0, 4).map((row) => (
          <div
            key={row.label}
            className="min-w-0 rounded-xs border border-border-subtle bg-black/30 px-2 py-1.5"
          >
            <span className="block truncate text-[10px] text-text-secondary">{text(row.label)}</span>
            <span
              className={cn(
                "block truncate font-mono text-caption",
                row.status === "ready" ? "text-brand-emerald-bright" : "text-text-muted"
              )}
            >
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MapZoomControls({
  scale,
  onZoomIn,
  onZoomOut,
  onReset,
}: {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}) {
  const { text } = useI18n();
  return (
    <div
      data-testid="world-map-zoom-controls"
      className="absolute bottom-4 right-4 z-30 flex items-center gap-1 rounded-sm border border-white/[0.12] bg-black/42 p-1 shadow-data-panel backdrop-blur-2xl"
    >
      <button
        type="button"
        onClick={onZoomOut}
        className="flex h-8 w-8 items-center justify-center rounded-xs text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
        aria-label={text("缩小")}
        title={text("缩小")}
      >
        <Minus className="h-4 w-4" />
      </button>
      <div className="min-w-12 text-center font-mono text-caption text-text-muted">{Math.round(scale * 100)}%</div>
      <button
        type="button"
        onClick={onZoomIn}
        className="flex h-8 w-8 items-center justify-center rounded-xs text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
        aria-label={text("放大")}
        title={text("放大")}
      >
        <Plus className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={onReset}
        className="flex h-8 w-8 items-center justify-center rounded-xs text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
        aria-label={text("重置视图")}
        title={text("重置视图")}
      >
        <RotateCcw className="h-4 w-4" />
      </button>
    </div>
  );
}

function RegionInsightModal({
  region,
  scopedEventId,
  onClose,
}: {
  region: WorldMapRegion;
  scopedEventId: string | null;
  onClose: () => void;
}) {
  const { lang, text } = useI18n();
  const color = riskColor(region.riskLevel);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const onCloseRef = useRef(onClose);
  const headline = lang === "zh" ? region.story.headlineZh : region.story.headlineEn;
  const regionName = lang === "zh" ? region.nameZh : region.nameEn;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = "hidden";

    const focusFrame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus({ preventScroll: true });
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onCloseRef.current();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousActiveElement && document.contains(previousActiveElement)) {
        previousActiveElement.focus({ preventScroll: true });
      }
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[90] overflow-hidden">
      <button
        type="button"
        aria-label={text("关闭")}
        className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={headline}
        data-testid="world-map-region-dossier"
        className="absolute bottom-3 left-3 right-3 max-h-[86vh] overflow-hidden rounded-sm border border-white/[0.13] bg-black/54 shadow-[0_28px_90px_rgba(0,0,0,0.52),inset_1px_0_0_rgba(255,255,255,0.07)] backdrop-blur-2xl md:bottom-3 md:left-auto md:right-3 md:top-3 md:max-h-none md:w-[min(520px,calc(100vw-112px))]"
      >
        <div className="border-b border-border-subtle px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="mb-2 flex items-center gap-2 text-caption font-semibold uppercase tracking-[0.18em] text-brand-cyan">
                <Route className="h-3.5 w-3.5" />
                {text("区域情报档案")}
                <span className="text-text-muted">/</span>
                <span className="truncate normal-case tracking-normal text-text-secondary">{regionName}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold leading-tight text-text-primary">{headline}</h2>
                <Badge variant={region.riskScore >= 72 ? "high" : region.riskScore >= 55 ? "medium" : "low"}>
                  {text(riskLabel(region.riskLevel))}
                </Badge>
              </div>
              <p className="mt-2 text-xs leading-5 text-text-secondary">
                {lang === "zh" ? region.narrativeZh : region.narrativeEn}
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              data-testid="world-map-region-dossier-close"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xs border border-border-subtle bg-black/45 text-text-muted hover:border-brand-cyan/35 hover:text-text-primary"
              aria-label={text("关闭")}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(86vh-128px)] overflow-y-auto p-4 md:max-h-[calc(100vh-140px)]">
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-[150px_minmax(0,1fr)] md:grid-cols-1">
              <div className="rounded-sm border border-white/[0.12] bg-white/[0.045] p-4 backdrop-blur-xl">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-caption text-text-muted">{text("区域综合风险")}</div>
                    <div className="mt-1 font-mono text-5xl font-semibold" style={{ color: color.text }}>
                      {region.riskScore}
                    </div>
                  </div>
                  <Activity className="h-6 w-6" style={{ color: color.text }} />
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-bg-surface-raised">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${region.riskScore}%`, background: color.text }}
                  />
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <DatabaseZap className="h-4 w-4 text-brand-emerald-bright" />
                  {text("区域运行态")}
                </div>
                <RuntimeGrid region={region} />
              </div>
            </div>

            {scopedEventId && <ScopedEventContextCard region={region} eventId={scopedEventId} />}
            <RiskReadingPathCard region={region} />
            <RiskMomentumCard region={region} />
            <EvidenceHealthCard region={region} />
            <EventQualityCard region={region} />
            <RiskActionCard region={region} />

            <InsightSection icon={Route} title={text("商品传导链")}>
              <StoryChain steps={region.story.chain} />
            </InsightSection>

            <InsightSection icon={Sparkles} title={text("动态预警")}>
              <div className="grid grid-cols-1 gap-3">
                {region.adaptiveAlerts.map((alert) => (
                  <AdaptiveAlertCard key={alert.id} alert={alert} />
                ))}
              </div>
            </InsightSection>

            <div className="grid grid-cols-1 gap-4">
              <InsightSection icon={ListChecks} title={text("证据")} compact>
                <EvidenceList region={region} kind="evidence" />
              </InsightSection>
              <InsightSection icon={AlertTriangle} title={text("反证")} compact>
                <EvidenceList region={region} kind="counterEvidence" />
              </InsightSection>
            </div>

            <InsightSection icon={CloudRain} title={text("天气异常")}>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 md:grid-cols-1">
                <WeatherMetric
                  label={text("降水距平")}
                  value={`${region.weather.precipitationAnomalyPct >= 0 ? "+" : ""}${region.weather.precipitationAnomalyPct.toFixed(1)}%`}
                  tone={region.weather.precipitationAnomalyPct >= 0 ? "up" : "down"}
                />
                <WeatherMetric
                  label={text("7日降水")}
                  value={`${region.weather.rainfall7dMm.toFixed(0)} mm`}
                  tone="neutral"
                />
                <WeatherMetric
                  label={text("洪涝风险")}
                  value={`${Math.round(region.weather.floodRisk * 100)}%`}
                  tone={region.weather.floodRisk > 0.55 ? "warning" : "neutral"}
                />
                {region.weather.currentTemperatureC != null && (
                  <WeatherMetric
                    label={text("当前气温")}
                    value={`${region.weather.currentTemperatureC.toFixed(1)} C`}
                    tone={region.weather.currentTemperatureC >= 32 ? "warning" : "neutral"}
                  />
                )}
                {region.weather.precipitation1hMm != null && (
                  <WeatherMetric
                    label={text("1小时降水")}
                    value={`${region.weather.precipitation1hMm.toFixed(1)} mm`}
                    tone={region.weather.precipitation1hMm >= 5 ? "warning" : "neutral"}
                  />
                )}
                {region.weather.humidityPct != null && (
                  <WeatherMetric
                    label={text("湿度")}
                    value={`${region.weather.humidityPct.toFixed(0)}%`}
                    tone="neutral"
                  />
                )}
                {region.weather.windKph != null && (
                  <WeatherMetric
                    label={text("风速")}
                    value={`${region.weather.windKph.toFixed(0)} km/h`}
                    tone={region.weather.windKph >= 35 ? "warning" : "neutral"}
                  />
                )}
                {region.weather.precipitationPercentile != null && (
                  <WeatherMetric
                    label={text("降水分位")}
                    value={`${region.weather.precipitationPercentile.toFixed(0)}%`}
                    tone={region.weather.precipitationPercentile >= 70 ? "warning" : "neutral"}
                  />
                )}
                {region.weather.temperaturePercentile != null && (
                  <WeatherMetric
                    label={text("温度分位")}
                    value={`${region.weather.temperaturePercentile.toFixed(0)}%`}
                    tone={region.weather.temperaturePercentile >= 70 ? "warning" : "neutral"}
                  />
                )}
              </div>
              <div className="mt-3 text-caption text-text-muted">
                {text("数据源")}：{region.weather.dataSource}
              </div>
            </InsightSection>
          </div>
        </div>
      </aside>
    </div>
  );
}

function RuntimeGrid({ region }: { region: WorldMapRegion }) {
  const { text } = useI18n();
  const eventIntelligence = region.runtime.eventIntelligence ?? 0;
  return (
    <div className="grid grid-cols-2 gap-2">
      <RuntimePill icon={AlertTriangle} label={text("预警")} value={region.runtime.alerts} />
      <RuntimePill icon={DatabaseZap} label={text("新闻")} value={region.runtime.newsEvents} />
      <RuntimePill icon={Activity} label={text("信号")} value={region.runtime.signals} />
      <RuntimePill icon={ShieldAlert} label={text("持仓")} value={region.runtime.positions} />
      <RuntimePill icon={Link2} label={text("事件智能")} value={eventIntelligence} />
    </div>
  );
}

function ScopedEventContextCard({
  region,
  eventId,
}: {
  region: WorldMapRegion;
  eventId: string;
}) {
  const { lang, text } = useI18n();
  const matchedEvidence = scopedEventEvidence(region, eventId);
  const hasCausalScope = region.causalScope.eventIds.includes(`event_intelligence:${eventId}`);
  const eventShortId = eventId.slice(0, 8);

  return (
    <section className="rounded-sm border border-brand-cyan/25 bg-brand-cyan/10 p-3 shadow-inner-panel backdrop-blur-xl">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-brand-cyan">
            <GitBranch className="h-4 w-4 shrink-0" />
            <span>{text("当前事件作用域")}</span>
          </div>
          <p className="mt-1 text-caption leading-4 text-text-secondary">
            {text(
              matchedEvidence.length > 0 || hasCausalScope
                ? "地图已按这条事件智能链过滤，以下证据解释它为什么命中当前区域。"
                : "当前区域未找到该事件智能链的直接证据，仅保留同品种 / 同机制观察。"
            )}
          </p>
        </div>
        <span className="rounded-xs border border-brand-cyan/25 bg-black/28 px-2 py-0.5 font-mono text-[10px] text-brand-cyan">
          EI:{eventShortId}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <ScopedEventMetric label={text("命中证据")} value={matchedEvidence.length} />
        <ScopedEventMetric label={text("事件作用域")} value={hasCausalScope ? text("命中") : text("未命中")} />
        <ScopedEventMetric label={text("质量门")} value={`${region.eventQuality.score}/100`} />
      </div>

      {matchedEvidence.length > 0 && (
        <div className="mt-3 space-y-2">
          {matchedEvidence.slice(0, 3).map((item) => (
            <div
              key={`${item.source}-${item.titleZh}`}
              className="rounded-xs border border-white/[0.1] bg-black/24 px-2.5 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate text-xs font-semibold text-text-primary">
                  {lang === "zh" ? item.titleZh : item.titleEn}
                </span>
                <span className="font-mono text-caption text-brand-orange">{Math.round(item.weight * 100)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[10px] text-text-muted">
                <span>{text(evidenceKindLabel(item.kind))}</span>
                <span className="truncate font-mono">{item.source}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ScopedEventMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-xs border border-white/[0.1] bg-black/24 px-2 py-1.5">
      <span className="block truncate text-[10px] text-text-muted">{label}</span>
      <span className="mt-0.5 block truncate font-mono text-caption text-text-primary">{value}</span>
    </div>
  );
}

function scopedEventEvidence(region: WorldMapRegion, eventId: string) {
  const token = `event_intelligence:${eventId}`;
  return [...region.story.evidence, ...region.story.counterEvidence].filter((item) =>
    item.source.includes(token)
  );
}

function evidenceKindLabel(kind: WorldMapRegion["story"]["evidence"][number]["kind"]) {
  const labels: Record<typeof kind, string> = {
    weather: "天气",
    alert: "预警",
    news: "新闻",
    signal: "信号",
    position: "持仓",
    event_intelligence: "事件智能",
    baseline: "基线",
  };
  return labels[kind] ?? kind;
}

function RiskReadingPathCard({ region }: { region: WorldMapRegion }) {
  const { text } = useI18n();
  const momentum = regionRiskMomentum(region);
  const momentumTone = momentumColor(momentum.direction);
  const health = regionEvidenceHealth(region);
  const quality = region.eventQuality;
  const qualityMeta = worldMapQualityMeta(quality.status);
  const causalTone = region.causalScope.hasDirectLinks ? "#22d3ee" : "#a3a3a3";
  const steps: Array<{
    icon: ComponentType<{ className?: string; style?: CSSProperties }>;
    label: string;
    value: string;
    detail: string;
    color: string;
  }> = [
    {
      icon: Activity,
      label: text("风险动量"),
      value: text(momentumLabel(momentum.direction)),
      detail: `${momentum.delta > 0 ? "+" : ""}${momentum.delta}`,
      color: momentumTone.text,
    },
    {
      icon: DatabaseZap,
      label: text("证据健康"),
      value: `${health.densityScore}/100`,
      detail: `${text("新鲜来源")} ${health.freshRuntimeSources}/${health.runtimeSources}`,
      color: "#22d3ee",
    },
    {
      icon: qualityMeta.icon,
      label: text("事件质量门"),
      value: `${quality.score}/100`,
      detail: text(qualityMeta.label),
      color: qualityMeta.color,
    },
    {
      icon: Link2,
      label: text("因果网络"),
      value: region.causalScope.hasDirectLinks ? text("可追溯") : text("同商品"),
      detail: `${region.causalScope.eventIds.length} ${text("事件作用域")}`,
      color: causalTone,
    },
  ];

  return (
    <section
      data-testid="world-map-reading-path"
      className="rounded-sm border border-white/[0.12] bg-white/[0.04] p-3 backdrop-blur-xl"
    >
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
        <Route className="h-4 w-4 text-brand-cyan" />
        {text("链路总览")}
      </div>
      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <div
              key={step.label}
              className="min-w-0 rounded-xs border bg-bg-base/70 px-2.5 py-2"
              style={{ borderColor: `${step.color}55` }}
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1.5 text-caption text-text-muted">
                  <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: step.color }} />
                  <span className="truncate">{step.label}</span>
                </span>
                <span className="font-mono text-[10px] text-text-muted">0{index + 1}</span>
              </div>
              <div className="truncate text-xs font-semibold text-text-primary">{step.value}</div>
              <div className="mt-0.5 truncate font-mono text-[10px]" style={{ color: step.color }}>
                {step.detail}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RiskMomentumCard({ region }: { region: WorldMapRegion }) {
  const { lang, text } = useI18n();
  const momentum = regionRiskMomentum(region);
  const tone = momentumColor(momentum.direction);
  const changedAt = formatOptionalUpdateTime(momentum.changedAt);

  return (
    <div className="rounded-sm border bg-white/[0.035] p-3 backdrop-blur-xl" style={{ borderColor: `${tone.text}55` }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 text-sm font-semibold" style={{ color: tone.text }}>
            <Activity className="h-4 w-4 shrink-0" />
            <span>{text("风险动量")}</span>
            <span>{text(momentumLabel(momentum.direction))}</span>
          </div>
          <p className="mt-1 line-clamp-2 text-caption leading-4 text-text-secondary">
            {lang === "zh" ? momentum.reasonZh : momentum.reasonEn}
          </p>
        </div>
        <span className="shrink-0 font-mono text-lg font-semibold" style={{ color: tone.text }}>
          {momentumSymbol(momentum.direction)}
          {momentum.delta > 0 ? "+" : ""}
          {momentum.delta}
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-bg-surface-raised">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(6, momentum.intensity * 100)}%`, background: tone.text }}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-xs border border-border-subtle bg-bg-base/70 px-2 py-2">
          <div className="text-caption text-text-muted">{text("动量来源")}</div>
          <div className="mt-1 truncate text-xs text-text-primary">
            {lang === "zh" ? momentum.driverZh : momentum.driverEn}
          </div>
        </div>
        <div className="rounded-xs border border-border-subtle bg-bg-base/70 px-2 py-2">
          <div className="text-caption text-text-muted">{text("触发时间")}</div>
          <div className="mt-1 font-mono text-xs text-text-primary">{changedAt ?? text("暂无")}</div>
        </div>
      </div>
    </div>
  );
}

function EventQualityCard({ region }: { region: WorldMapRegion }) {
  const { text } = useI18n();
  const quality = region.eventQuality;
  const meta = worldMapQualityMeta(quality.status);
  const Icon = meta.icon;

  return (
    <div
      className="rounded-sm border bg-white/[0.035] p-3 backdrop-blur-xl"
      style={{ borderColor: `${meta.color}55` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex min-w-0 items-center gap-2 text-sm font-semibold" style={{ color: meta.color }}>
          <Icon className="h-4 w-4 shrink-0" />
          <span>{text("事件质量门")}</span>
          <span>{text(meta.label)}</span>
        </div>
        <span className="font-mono text-sm text-text-primary">{quality.score}/100</span>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-2">
        <EventQualityMetric label="质量通过" value={quality.passed} tone="up" />
        <EventQualityMetric label="复核" value={quality.review} tone="warn" />
        <EventQualityMetric label="阻断" value={quality.blocked} tone="down" />
        <EventQualityMetric label="总数" value={quality.total} tone="neutral" />
      </div>
      {quality.total > 0 && quality.passed === 0 && (
        <div className="mt-2 rounded-xs border border-brand-orange/25 bg-brand-orange/10 px-2 py-1.5 text-caption leading-relaxed text-brand-orange">
          {text("当前区域事件智能尚未通过质量门，地图只用于阅读复核，不放大自动风险。")}
        </div>
      )}
    </div>
  );
}

function RiskActionCard({ region }: { region: WorldMapRegion }) {
  const { text } = useI18n();
  const action = regionRiskAction(region);
  const Icon = action.icon;
  const PrimaryIcon = action.primaryIcon;
  const SecondaryIcon = action.secondaryIcon;

  return (
    <section
      data-testid="world-map-risk-action"
      className="rounded-sm border bg-white/[0.04] p-3 backdrop-blur-xl"
      style={{ borderColor: `${action.color}55` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 text-sm font-semibold" style={{ color: action.color }}>
            <Icon className="h-4 w-4 shrink-0" />
            <span>{text("推荐动作")}</span>
          </div>
          <div className="mt-1 text-sm font-semibold text-text-primary">{text(action.title)}</div>
          <p className="mt-1 text-caption leading-4 text-text-secondary">{text(action.description)}</p>
        </div>
        <span className="rounded-xs border border-white/[0.12] bg-black/28 px-2 py-0.5 font-mono text-[10px] text-text-muted">
          D.5
        </span>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Link
          href={action.primaryHref}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-sm border text-sm font-semibold transition-colors"
          style={{ borderColor: `${action.color}66`, background: `${action.color}18`, color: action.color }}
        >
          <PrimaryIcon className="h-4 w-4" />
          {text(action.primaryLabel)}
        </Link>
        <Link
          href={action.secondaryHref}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-sm border border-border-subtle bg-black/28 text-sm font-semibold text-text-secondary transition-colors hover:border-brand-cyan/35 hover:text-text-primary"
        >
          <SecondaryIcon className="h-4 w-4" />
          {text(action.secondaryLabel)}
        </Link>
      </div>
    </section>
  );
}

function EvidenceHealthCard({ region }: { region: WorldMapRegion }) {
  const { text } = useI18n();
  const health = regionEvidenceHealth(region);
  const weakEvidence = health.densityScore < 45 || health.sourceReliability < 45;

  return (
    <div className="rounded-sm border border-brand-cyan/20 bg-white/[0.035] p-3 backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex min-w-0 items-center gap-2 text-sm font-semibold text-brand-cyan">
          <DatabaseZap className="h-4 w-4 shrink-0" />
          <span>{text("证据健康")}</span>
        </div>
        <span className="font-mono text-sm text-text-primary">{health.densityScore}/100</span>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2">
        <EvidenceHealthMetric label={text("支持证据")} value={health.evidenceCount} />
        <EvidenceHealthMetric label={text("反证")} value={health.counterEvidenceCount} />
        <EvidenceHealthMetric label={text("来源数")} value={health.runtimeSources} />
        <EvidenceHealthMetric label={text("新鲜来源")} value={health.freshRuntimeSources} />
      </div>

      <div className="mt-3 space-y-2">
        <EvidenceHealthBar label={text("证据密度")} value={health.densityScore} tone="cyan" />
        <EvidenceHealthBar label={text("来源可信度")} value={health.sourceReliability} tone="green" />
        <EvidenceHealthBar label={text("数据新鲜度")} value={health.freshnessScore} tone="orange" />
      </div>

      {weakEvidence && (
        <div className="mt-3 rounded-xs border border-brand-orange/25 bg-brand-orange/10 px-2 py-1.5 text-caption leading-relaxed text-brand-orange">
          {text("当前区域证据覆盖偏薄，建议先阅读证据与反证，再判断是否需要进入因果网络。")}
        </div>
      )}
    </div>
  );
}

function EvidenceHealthMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xs border border-border-subtle bg-bg-base/70 px-2 py-2">
      <div className="text-caption text-text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function EvidenceHealthBar({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "cyan" | "green" | "orange";
}) {
  const colorClass = {
    cyan: "bg-brand-cyan",
    green: "bg-brand-emerald-bright",
    orange: "bg-brand-orange",
  }[tone];
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-caption">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono text-text-primary">{value}/100</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-bg-surface-raised">
        <div className={cn("h-full rounded-full", colorClass)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function EventQualityMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "up" | "warn" | "down" | "neutral";
}) {
  const { text } = useI18n();
  const toneClass = {
    up: "text-brand-emerald-bright",
    warn: "text-brand-orange",
    down: "text-data-down",
    neutral: "text-text-secondary",
  }[tone];
  return (
    <div className="rounded-xs border border-border-subtle bg-bg-base/70 px-2 py-2">
      <div className="text-caption text-text-muted">{text(label)}</div>
      <div className={cn("mt-1 font-mono text-sm", toneClass)}>{value}</div>
    </div>
  );
}

function RuntimePill({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-sm border border-border-subtle bg-bg-base p-3">
      <div className="flex items-center gap-2 text-caption text-text-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-2 font-mono text-xl text-text-primary">{value}</div>
    </div>
  );
}

function InsightSection({
  icon: Icon,
  title,
  compact,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  compact?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={cn("rounded-sm border border-white/[0.12] bg-white/[0.045] p-4 backdrop-blur-xl", compact && "h-full")}>
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
        <Icon className="h-4 w-4 text-brand-emerald-bright" />
        {title}
      </div>
      {children}
    </section>
  );
}

function AdaptiveAlertCard({ alert }: { alert: WorldMapAdaptiveAlert }) {
  const { lang, text } = useI18n();
  const color = riskColor(alert.severity);
  return (
    <div className="rounded-sm border border-white/[0.12] bg-white/[0.045] p-3 backdrop-blur-xl">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-semibold text-text-primary">
          {lang === "zh" ? alert.titleZh : alert.titleEn}
        </div>
        <span className="font-mono text-caption" style={{ color: color.text }}>
          {Math.round(alert.confidence * 100)}%
        </span>
      </div>
      <div className="mt-2 text-xs text-text-secondary">
        {lang === "zh" ? alert.mechanismZh : alert.mechanismEn}
      </div>
      <div className="mt-3 text-caption text-text-muted">
        {text("来源")}：{text(alert.source)}
      </div>
    </div>
  );
}

function StoryChain({ steps }: { steps: WorldMapStoryStep[] }) {
  const { lang, text } = useI18n();
  return (
    <div className="space-y-2">
      {steps.map((step, index) => (
        <div
          key={`${step.stage}-${index}`}
          className="relative grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-sm border border-white/[0.12] bg-white/[0.045] p-3 backdrop-blur-xl"
        >
          <div className="relative flex justify-center">
            <span className="z-10 flex h-6 w-6 items-center justify-center rounded-full border border-brand-cyan/35 bg-brand-cyan/10 font-mono text-[10px] text-brand-cyan">
              {index + 1}
            </span>
            {index < steps.length - 1 && (
              <span className="absolute left-1/2 top-7 h-[calc(100%+8px)] w-px -translate-x-1/2 bg-brand-cyan/18" />
            )}
          </div>
          <div className="min-w-0">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-caption text-brand-cyan">{text(stageLabel(step.stage))}</span>
              <span className="font-mono text-caption text-text-muted">
                {Math.round(step.confidence * 100)}%
              </span>
            </div>
            <div className="text-sm leading-5 text-text-primary">{lang === "zh" ? step.labelZh : step.labelEn}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function EvidenceList({
  region,
  kind,
}: {
  region: WorldMapRegion;
  kind: "evidence" | "counterEvidence";
}) {
  const { lang, text } = useI18n();
  const rows = region.story[kind];
  if (rows.length === 0) {
    return (
      <div className="rounded-xs border border-white/[0.12] bg-white/[0.04] px-3 py-2 text-caption text-text-muted backdrop-blur-xl">
        {text(kind === "evidence" ? "暂无支持证据" : "暂无反证")}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={`${row.source}-${row.titleZh}`} className="rounded-xs border border-white/[0.12] bg-white/[0.04] px-3 py-2 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-text-primary">{lang === "zh" ? row.titleZh : row.titleEn}</span>
            <span className="font-mono text-caption text-text-muted">{Math.round(row.weight * 100)}%</span>
          </div>
          <div className="mt-1 text-caption text-text-muted">
            {text(row.kind)} · {row.source}
          </div>
        </div>
      ))}
    </div>
  );
}

function WeatherMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "up" | "down" | "warning" | "neutral";
}) {
  return (
    <div className="rounded-sm border border-white/[0.12] bg-white/[0.045] px-3 py-2 backdrop-blur-xl">
      <div className="text-caption text-text-muted">{label}</div>
      <div
        className={cn(
          "mt-1 font-mono text-sm",
          tone === "up" && "text-data-up",
          tone === "down" && "text-data-down",
          tone === "warning" && "text-brand-orange",
          tone === "neutral" && "text-text-primary"
        )}
      >
        {value}
      </div>
    </div>
  );
}

function project(point: GeoPoint, projection: GeoProjection): { x: number; y: number } {
  const projected = projection([point.lon, point.lat]);
  if (!projected) {
    return { x: MAP_WIDTH / 2, y: MAP_HEIGHT / 2 };
  }
  return {
    x: projected[0],
    y: projected[1],
  };
}

function computeMapViewport(view: MapViewTransform, projection: GeoProjection): WorldMapViewport {
  const padding = 80;
  const samples: Array<[number, number]> = [
    [-padding, -padding],
    [MAP_WIDTH / 2, -padding],
    [MAP_WIDTH + padding, -padding],
    [-padding, MAP_HEIGHT / 2],
    [MAP_WIDTH / 2, MAP_HEIGHT / 2],
    [MAP_WIDTH + padding, MAP_HEIGHT / 2],
    [-padding, MAP_HEIGHT + padding],
    [MAP_WIDTH / 2, MAP_HEIGHT + padding],
    [MAP_WIDTH + padding, MAP_HEIGHT + padding],
  ];
  const coords = samples.flatMap(([screenX, screenY]) => {
    const mapX = (screenX - view.x) / view.scale;
    const mapY = (screenY - view.y) / view.scale;
    const inverted = projection.invert?.([mapX, mapY]);
    if (!inverted) return [];
    const [lon, lat] = inverted;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return [];
    return [{ lat: clamp(lat, -85, 85), lon: clamp(lon, -180, 180) }];
  });
  if (coords.length === 0) {
    return { minLat: -85, maxLat: 85, minLon: -180, maxLon: 180 };
  }

  const latitudes = coords.map((coord) => coord.lat);
  const longitudes = coords.map((coord) => coord.lon);
  const latSpan = ensureMinSpan(Math.min(...latitudes), Math.max(...latitudes), -85, 85);
  const lonSpan = ensureMinSpan(Math.min(...longitudes), Math.max(...longitudes), -180, 180);

  return {
    minLat: latSpan.min,
    maxLat: latSpan.max,
    minLon: lonSpan.min,
    maxLon: lonSpan.max,
  };
}

function ensureMinSpan(min: number, max: number, floor: number, ceiling: number): { min: number; max: number } {
  if (max - min >= 1) return { min, max };
  const center = (min + max) / 2;
  return {
    min: clamp(center - 0.5, floor, ceiling - 1),
    max: clamp(center + 0.5, floor + 1, ceiling),
  };
}

function polygonPath(points: GeoPoint[], projection: GeoProjection): string {
  return `${points
    .map((point, index) => {
      const projected = project(point, projection);
      return `${index === 0 ? "M" : "L"}${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`;
    })
    .join(" ")} Z`;
}

function arcPath(from: GeoPoint, to: GeoPoint, projection: GeoProjection): string | null {
  const start = project(from, projection);
  const end = project(to, projection);
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2;
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  if (!Number.isFinite(distance) || distance < 24) return null;

  const bend = Math.min(58, Math.max(22, distance * 0.16));
  return `M${start.x.toFixed(1)} ${start.y.toFixed(1)} Q${midX.toFixed(1)} ${(midY - bend).toFixed(1)} ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function buildMapLibreRegionCollection(regions: WorldMapRegion[]): MapLibreRegionFeatureCollection {
  return {
    type: "FeatureCollection",
    features: regions.map((region) => {
      const coordinates = region.polygon.map((point) => [point.lon, point.lat]);
      const first = coordinates[0];
      const last = coordinates[coordinates.length - 1];
      const closedCoordinates =
        first && last && (first[0] !== last[0] || first[1] !== last[1])
          ? [...coordinates, first]
          : coordinates;

      return {
        type: "Feature",
        id: region.id,
        properties: {
          id: region.id,
          riskLevel: region.riskLevel,
          riskScore: region.riskScore,
        },
        geometry: {
          type: "Polygon",
          coordinates: [closedCoordinates],
        },
      };
    }),
  };
}

function buildMapLibreStyle(
  regionCollection: MapLibreRegionFeatureCollection,
  showRiskRegions: boolean
): StyleSpecification {
  return {
    version: 8,
    sources: {
      countries: {
        type: "geojson",
        data: WORLD_COUNTRIES,
      },
      "risk-regions": {
        type: "geojson",
        data: regionCollection,
      },
    },
    layers: [
      {
        id: "ocean-background",
        type: "background",
        paint: {
          "background-color": "#020504",
        },
      },
      {
        id: "country-fill",
        type: "fill",
        source: "countries",
        paint: {
          "fill-color": "#07211d",
          "fill-opacity": 0.48,
        },
      },
      {
        id: "country-line",
        type: "line",
        source: "countries",
        paint: {
          "line-color": "rgba(34,211,238,0.24)",
          "line-width": 0.45,
        },
      },
      {
        id: "risk-region-fill",
        type: "fill",
        source: "risk-regions",
        layout: {
          visibility: showRiskRegions ? "visible" : "none",
        },
        paint: {
          "fill-color": [
            "match",
            ["get", "riskLevel"],
            "critical",
            "#ff4d4f",
            "high",
            "#f97316",
            "elevated",
            "#f59e0b",
            "watch",
            "#22d3ee",
            "#10b981",
          ],
          "fill-opacity": ["interpolate", ["linear"], ["get", "riskScore"], 0, 0.08, 100, 0.36],
        },
      },
      {
        id: "risk-region-line",
        type: "line",
        source: "risk-regions",
        layout: {
          visibility: showRiskRegions ? "visible" : "none",
        },
        paint: {
          "line-color": [
            "match",
            ["get", "riskLevel"],
            "critical",
            "#ff4d4f",
            "high",
            "#f97316",
            "elevated",
            "#f59e0b",
            "watch",
            "#22d3ee",
            "#10b981",
          ],
          "line-opacity": 0.72,
          "line-width": 1.25,
        },
      },
    ],
  } as StyleSpecification;
}

function setMapLibreLayerVisibility(map: MapLibreMap, layerIds: string[], visible: boolean): void {
  for (const layerId of layerIds) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
    }
  }
}

function projectTileCell(cell: WorldMapTileCell, projection: GeoProjection): ProjectedTileCell {
  return {
    polygon: cell.polygon.map((point) => {
      const projected = project(point, projection);
      return [projected.x, projected.y, 0];
    }),
  };
}

function weatherTileTone(cell: WorldMapTileCell): string {
  if (cell.metric === "drought_risk") return "#f97316";
  if (cell.metric === "precipitation_anomaly_pct" && cell.value < 0) return "#f97316";
  return "#22d3ee";
}

function buildWeatherTileCells(
  regions: WorldMapRegion[],
  projection: GeoProjection,
  tileCells: WorldMapTileCell[],
  maxCells: number
): WeatherTileCell[] {
  const backendCells = tileCells.filter((cell) => cell.layer === "weather");
  if (backendCells.length > 0) {
    return backendCells
      .map((cell) => {
        const projected = projectTileCell(cell, projection);
        const tone = weatherTileTone(cell);
        return {
          id: cell.id,
          polygon: projected.polygon,
          fillColor: colorToRgba(tone, 26 + cell.intensity * 92),
          lineColor: colorToRgba(tone, 24 + cell.intensity * 64),
          intensity: cell.intensity,
          regionId: cell.regionId,
        };
      })
      .sort((left, right) => right.intensity - left.intensity)
      .slice(0, maxCells);
  }

  const cellSize = 20;
  const cells = new Map<string, WeatherTileCell>();

  for (const region of regions) {
    const center = project(region.center, projection);
    const anomalyStress = Math.min(1, Math.abs(region.weather.precipitationAnomalyPct) / 85);
    const floodStress = region.weather.floodRisk;
    const droughtStress = region.weather.droughtRisk;
    const weatherStress = Math.max(anomalyStress, floodStress, droughtStress);
    const radius = 1 + Math.round(weatherStress * 2);
    const tone =
      droughtStress > floodStress && region.weather.precipitationAnomalyPct < 0 ? "#f97316" : "#22d3ee";

    for (let column = -radius; column <= radius; column += 1) {
      for (let row = -radius; row <= radius; row += 1) {
        const distance = Math.hypot(column, row);
        if (distance > radius + 0.35) continue;

        const decay = 1 - distance / (radius + 0.85);
        const intensity = clamp(weatherStress * (0.45 + decay * 0.55), 0, 1);
        if (intensity < 0.16) continue;

        const x = center.x + column * cellSize;
        const y = center.y + row * cellSize;
        if (x < -cellSize || x > MAP_WIDTH + cellSize || y < -cellSize || y > MAP_HEIGHT + cellSize) continue;

        const gridX = Math.round(x / cellSize);
        const gridY = Math.round(y / cellSize);
        const id = `${gridX}:${gridY}`;
        const alpha = 26 + intensity * 92;
        const previous = cells.get(id);
        if (!previous || previous.intensity < intensity) {
          const left = gridX * cellSize - cellSize / 2;
          const top = gridY * cellSize - cellSize / 2;
          const right = left + cellSize;
          const bottom = top + cellSize;
          cells.set(id, {
            id,
            polygon: [
              [left, top, 0],
              [right, top, 0],
              [right, bottom, 0],
              [left, bottom, 0],
            ],
            fillColor: colorToRgba(tone, alpha),
            lineColor: colorToRgba(tone, 24 + intensity * 64),
            intensity,
            regionId: region.id,
          });
        }
      }
    }
  }

  return Array.from(cells.values())
    .sort((left, right) => right.intensity - left.intensity)
    .slice(0, maxCells);
}

function buildRiskDensityCells(
  regions: WorldMapRegion[],
  projection: GeoProjection,
  tileCells: WorldMapTileCell[],
  maxCells: number
): RiskDensityCell[] {
  const backendCells = tileCells.filter((cell) => cell.layer === "risk");
  if (backendCells.length > 0) {
    return backendCells
      .map((cell) => {
        const center = project(cell.center, projection);
        return {
          id: cell.id,
          x: center.x,
          y: center.y,
          size: 18 + cell.intensity * 14,
          intensity: cell.intensity,
          riskLevel: cell.riskLevel,
          regionId: cell.regionId,
        };
      })
      .sort((left, right) => right.intensity - left.intensity)
      .slice(0, maxCells);
  }

  const cellSize = 24;
  const cells = new Map<string, RiskDensityCell>();

  for (const region of regions) {
    const center = project(region.center, projection);
    const weatherStress = Math.max(
      region.weather.floodRisk,
      region.weather.droughtRisk,
      Math.min(1, Math.abs(region.weather.precipitationAnomalyPct) / 80)
    );
    const riskWeight = region.riskScore / 100;
    const radius = 2 + Math.round(weatherStress * 2);

    for (let column = -radius; column <= radius; column += 1) {
      for (let row = -radius; row <= radius; row += 1) {
        const distance = Math.hypot(column, row);
        if (distance > radius + 0.35) continue;

        const decay = 1 - distance / (radius + 0.85);
        const intensity = clamp(riskWeight * (0.62 + weatherStress * 0.38) * decay, 0, 1);
        if (intensity < 0.12) continue;

        const x = center.x + column * cellSize;
        const y = center.y + row * cellSize;
        if (x < -cellSize || x > MAP_WIDTH + cellSize || y < -cellSize || y > MAP_HEIGHT + cellSize) continue;

        const gridX = Math.round(x / cellSize);
        const gridY = Math.round(y / cellSize);
        const id = `${gridX}:${gridY}`;
        const previous = cells.get(id);
        if (!previous || previous.intensity < intensity) {
          cells.set(id, {
            id,
            x: gridX * cellSize,
            y: gridY * cellSize,
            size: cellSize * (0.72 + intensity * 0.28),
            intensity,
            riskLevel: region.riskLevel,
            regionId: region.id,
          });
        }
      }
    }
  }

  return Array.from(cells.values())
    .sort((left, right) => right.intensity - left.intensity)
    .slice(0, Math.min(maxCells, 180));
}

function buildRegionMapLabels({
  projection,
  regions,
  renderBudget,
  riskDeltas,
  selectedId,
  view,
}: {
  projection: GeoProjection;
  regions: WorldMapRegion[];
  renderBudget: TileRuntimeBudget;
  riskDeltas: Record<string, number>;
  selectedId: string | null;
  view: MapViewTransform;
}): RegionMapLabel[] {
  if (regions.length === 0) return [];

  const maxLabels = worldMapLabelBudget(view.scale, renderBudget, regions.length);
  const labels: RegionMapLabel[] = [];
  const occupied: ScreenBox[] = [];
  const orderedRegions = regions
    .map((region, index) => ({
      index,
      priority: regionMapLabelPriority(region, selectedId, riskDeltas[region.id] ?? 0),
      region,
    }))
    .sort((left, right) => right.priority - left.priority || left.index - right.index);

  for (const { priority, region } of orderedRegions) {
    const selected = region.id === selectedId;
    if (!selected && labels.length >= maxLabels) continue;

    const center = project(region.center, projection);
    const screenCenter = mapPointToScreen(center, view);
    const width = selected ? WORLD_MAP_LABEL_SIZE.width + 16 : WORLD_MAP_LABEL_SIZE.width;
    const candidate = chooseRegionLabelCandidate(
      screenCenter,
      width,
      WORLD_MAP_LABEL_SIZE.height,
      occupied,
      selected
    );
    if (!candidate) continue;

    occupied.push(candidate.box);
    labels.push({
      anchorX: screenToMapX(candidate.anchorX, view),
      anchorY: screenToMapY(candidate.anchorY, view),
      height: WORLD_MAP_LABEL_SIZE.height,
      id: region.id,
      priority,
      width,
      x: screenToMapX(candidate.box.left, view),
      y: screenToMapY(candidate.box.top, view),
    });
  }

  return labels;
}

function worldMapLabelBudget(scale: number, renderBudget: TileRuntimeBudget, regionCount: number): number {
  const zoomBonus = scale >= 2.1 ? 6 : scale >= 1.55 ? 4 : scale >= 1.15 ? 2 : scale < 0.95 ? -2 : 0;
  return Math.round(clamp(WORLD_MAP_LABEL_BUDGETS[renderBudget] + zoomBonus, 1, regionCount));
}

function regionMapLabelPriority(
  region: WorldMapRegion,
  selectedId: string | null,
  riskDelta: number
): number {
  const momentum = regionRiskMomentum(region);
  const health = regionEvidenceHealth(region);
  let priority = region.riskScore;
  if (region.id === selectedId) priority += 10_000;
  if (region.causalScope.hasDirectLinks) priority += 30;
  priority += Math.min(region.runtime.highSeverityAlerts * 8, 36);
  priority += Math.min((region.runtime.eventIntelligence ?? 0) * 4, 28);
  priority += Math.min(region.eventQuality.passed * 4, 24);
  priority += Math.min(Math.abs(riskDelta) * 2, 26);
  priority += Math.round(momentum.intensity * 18);
  priority += Math.round(health.densityScore / 12);
  return priority;
}

function chooseRegionLabelCandidate(
  center: { x: number; y: number },
  width: number,
  height: number,
  occupied: ScreenBox[],
  allowClamp: boolean
): { anchorX: number; anchorY: number; box: ScreenBox } | null {
  const gap = 16;
  const candidates = [
    {
      anchorX: center.x + gap,
      anchorY: center.y,
      box: {
        bottom: center.y + height / 2,
        left: center.x + gap,
        right: center.x + gap + width,
        top: center.y - height / 2,
      },
    },
    {
      anchorX: center.x - gap,
      anchorY: center.y,
      box: {
        bottom: center.y + height / 2,
        left: center.x - gap - width,
        right: center.x - gap,
        top: center.y - height / 2,
      },
    },
    {
      anchorX: center.x,
      anchorY: center.y - gap,
      box: {
        bottom: center.y - gap,
        left: center.x - width / 2,
        right: center.x + width / 2,
        top: center.y - gap - height,
      },
    },
    {
      anchorX: center.x,
      anchorY: center.y + gap,
      box: {
        bottom: center.y + gap + height,
        left: center.x - width / 2,
        right: center.x + width / 2,
        top: center.y + gap,
      },
    },
  ];

  const preferred = candidates.find(
    (candidate) => boxFitsSafeArea(candidate.box) && !occupied.some((box) => boxesOverlap(candidate.box, box, 8))
  );
  if (preferred) return preferred;
  if (!allowClamp) return null;

  const clamped = clampScreenBox(candidates[0].box, WORLD_MAP_LABEL_SAFE_AREA);
  return {
    anchorX: clamped.left,
    anchorY: clamp(center.y, clamped.top + 6, clamped.bottom - 6),
    box: clamped,
  };
}

function mapPointToScreen(point: { x: number; y: number }, view: MapViewTransform): { x: number; y: number } {
  return {
    x: view.x + point.x * view.scale,
    y: view.y + point.y * view.scale,
  };
}

function screenToMapX(value: number, view: MapViewTransform): number {
  return (value - view.x) / view.scale;
}

function screenToMapY(value: number, view: MapViewTransform): number {
  return (value - view.y) / view.scale;
}

function boxFitsSafeArea(box: ScreenBox): boolean {
  return (
    box.left >= WORLD_MAP_LABEL_SAFE_AREA.left &&
    box.right <= WORLD_MAP_LABEL_SAFE_AREA.right &&
    box.top >= WORLD_MAP_LABEL_SAFE_AREA.top &&
    box.bottom <= WORLD_MAP_LABEL_SAFE_AREA.bottom
  );
}

function boxesOverlap(left: ScreenBox, right: ScreenBox, padding = 0): boolean {
  return !(
    left.right + padding < right.left ||
    left.left - padding > right.right ||
    left.bottom + padding < right.top ||
    left.top - padding > right.bottom
  );
}

function clampScreenBox(box: ScreenBox, bounds: ScreenBox): ScreenBox {
  const width = box.right - box.left;
  const height = box.bottom - box.top;
  const left = clamp(box.left, bounds.left, bounds.right - width);
  const top = clamp(box.top, bounds.top, bounds.bottom - height);
  return {
    bottom: top + height,
    left,
    right: left + width,
    top,
  };
}

function buildRiskRoutes(regions: WorldMapRegion[], maxRoutes: number): RiskRoute[] {
  return buildRiskBridges(regions)
    .slice(0, maxRoutes)
    .map((bridge) => ({
      id: bridge.id,
      from: bridge.source.center,
      to: bridge.target.center,
      weight: bridge.weight,
    }));
}

function buildRiskBridges(regions: WorldMapRegion[]): RiskBridge[] {
  const bridges: RiskBridge[] = [];
  for (let index = 0; index < regions.length; index += 1) {
    for (let nextIndex = index + 1; nextIndex < regions.length; nextIndex += 1) {
      const source = regions[index];
      const target = regions[nextIndex];
      const sharedSymbols = source.symbols.filter((symbol) => target.symbols.includes(symbol));
      const sharedCommodity =
        source.commodityZh === target.commodityZh || source.commodityEn === target.commodityEn;
      if (sharedSymbols.length === 0 && !sharedCommodity) continue;

      bridges.push({
        id: `${source.id}-${target.id}`,
        source,
        target,
        sharedSymbols,
        sharedCommodity,
        weight: Math.min(1, (source.riskScore + target.riskScore) / 200 + sharedSymbols.length * 0.1),
      });
    }
  }

  return bridges.sort((a, b) => b.weight - a.weight);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function clampMapView(view: MapViewTransform): MapViewTransform {
  const xLimit = MAP_WIDTH * Math.max(0.18, view.scale - 0.72);
  const yLimit = MAP_HEIGHT * Math.max(0.18, view.scale - 0.72);
  return {
    scale: view.scale,
    x: clamp(view.x, -xLimit, xLimit),
    y: clamp(view.y, -yLimit, yLimit),
  };
}

function formatUpdateTime(date: Date): string {
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatOptionalUpdateTime(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return formatUpdateTime(date);
}

function riskColor(level: WorldRiskLevel) {
  switch (level) {
    case "critical":
      return {
        text: "#ff4d4f",
        fill: "rgba(255,77,79,0.18)",
        stroke: "rgba(255,77,79,0.52)",
        strokeStrong: "#ff4d4f",
      };
    case "high":
      return {
        text: "#f97316",
        fill: "rgba(249,115,22,0.18)",
        stroke: "rgba(249,115,22,0.5)",
        strokeStrong: "#f97316",
      };
    case "elevated":
      return {
        text: "#f59e0b",
        fill: "rgba(245,158,11,0.16)",
        stroke: "rgba(245,158,11,0.45)",
        strokeStrong: "#f59e0b",
      };
    case "watch":
      return {
        text: "#22d3ee",
        fill: "rgba(34,211,238,0.13)",
        stroke: "rgba(34,211,238,0.42)",
        strokeStrong: "#22d3ee",
      };
    default:
      return {
        text: "#10b981",
        fill: "rgba(16,185,129,0.11)",
        stroke: "rgba(16,185,129,0.35)",
        strokeStrong: "#10b981",
      };
  }
}

function colorToRgba(hex: string, alpha: number): [number, number, number, number] {
  const normalized = hex.replace("#", "");
  const value = Number.parseInt(normalized, 16);
  if (!Number.isFinite(value)) return [16, 185, 129, alpha];
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255, alpha];
}

function worldMapQualityMeta(status: WorldMapRegion["eventQuality"]["status"]) {
  if (status === "decision_grade") {
    return { label: "决策级", color: "#10b981", icon: ShieldCheck };
  }
  if (status === "shadow_ready") {
    return { label: "影子可用", color: "#38bdf8", icon: Sparkles };
  }
  if (status === "review") {
    return { label: "质量复核", color: "#f97316", icon: ShieldAlert };
  }
  if (status === "blocked") {
    return { label: "质量阻断", color: "#ef4444", icon: ShieldX };
  }
  return { label: "未评估", color: "#a3a3a3", icon: ShieldAlert };
}

function riskLabel(level: WorldRiskLevel): string {
  const labels: Record<WorldRiskLevel, string> = {
    low: "低风险",
    watch: "观察",
    elevated: "升温",
    high: "高风险",
    critical: "极高风险",
  };
  return labels[level];
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    climate: "气候",
    weather_regime: "天气状态",
    production: "生产",
    logistics: "物流",
    supply: "供应",
    demand: "需求",
    inventory: "库存",
    policy: "政策",
    cost: "成本",
    market: "价格",
  };
  return labels[stage] ?? stage;
}

function worldMapFilterParams(
  filters: WorldMapScopeFilters,
  viewport?: WorldMapViewport | null
): WorldMapFilterParams {
  return {
    symbol: filters.symbol === "all" ? undefined : filters.symbol,
    mechanism: filters.mechanism === "all" ? undefined : filters.mechanism,
    source: filters.source === "all" ? undefined : filters.source,
    viewport: viewport ?? undefined,
  };
}

function worldMapTileCacheKey(
  filters: WorldMapScopeFilters,
  resolution: WorldMapTileResolution,
  viewport?: WorldMapViewport | null
) {
  const viewportKey = viewport
    ? [
        viewport.minLat,
        viewport.maxLat,
        viewport.minLon,
        viewport.maxLon,
      ].map((value) => value.toFixed(2)).join(":")
    : "global";

  return [
    filters.symbol,
    filters.mechanism,
    filters.source,
    resolution,
    viewportKey,
  ].join("|");
}

function rememberWorldMapTileSnapshot(
  cache: Map<string, WorldMapTileSnapshot>,
  key: string,
  snapshot: WorldMapTileSnapshot
) {
  if (cache.has(key)) {
    cache.delete(key);
  }
  cache.set(key, snapshot);

  while (cache.size > WORLD_MAP_TILE_CACHE_LIMIT) {
    const oldestKey = cache.keys().next().value;
    if (!oldestKey) return;
    cache.delete(oldestKey);
  }
}

function buildTileRuntimeMetrics(
  snapshot: WorldMapTileSnapshot,
  cacheEntries: number,
  resolution: WorldMapTileResolution,
  status: TileRuntimeStatus
): TileRuntimeMetrics {
  const totalCells = snapshot.cells.length;
  return {
    budget: tileRuntimeBudget(totalCells),
    cacheEntries,
    resolution,
    riskCells: snapshot.summary.riskCells,
    status,
    totalCells,
    weatherCells: snapshot.summary.weatherCells,
  };
}

function tileRuntimeBudget(totalCells: number): TileRuntimeBudget {
  if (totalCells >= 160) return "dense";
  if (totalCells >= 72) return "normal";
  return "light";
}

function tileBudgetLabel(budget: TileRuntimeBudget) {
  if (budget === "dense") return "密集负载";
  if (budget === "normal") return "标准负载";
  return "轻负载";
}

function tileBudgetTone(budget: TileRuntimeBudget) {
  if (budget === "dense") return "text-brand-orange";
  if (budget === "normal") return "text-brand-cyan";
  return "text-brand-emerald-bright";
}

function tileRuntimeStatusLabel(status: TileRuntimeStatus) {
  if (status === "cache_hit") return "瓦片缓存命中";
  if (status === "forced_refresh") return "已刷新";
  return "网络请求";
}
