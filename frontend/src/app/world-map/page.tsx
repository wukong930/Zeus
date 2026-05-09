"use client";

import Link from "next/link";
import { geoEqualEarth, geoGraticule, geoPath, type GeoPermissibleObjects, type GeoProjection } from "d3-geo";
import type { ComponentType, PointerEvent as ReactPointerEvent, ReactNode, WheelEvent as ReactWheelEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CloudRain,
  Compass,
  DatabaseZap,
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
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import {
  fetchWorldMapSnapshot,
  type GeoPoint,
  type WorldMapAdaptiveAlert,
  type WorldMapLayer,
  type WorldMapRegion,
  type WorldMapSnapshot,
  type WorldMapStoryStep,
  type WorldRiskLevel,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type CommodityFilter = "all" | string;
type WorldMapVisualLayer = "weather" | "density" | "heat" | "routes" | "labels";
type WorldMapRendererMode = "svg" | "webgl-ready";
type VisibleMapLayers = Record<WorldMapVisualLayer, boolean>;
type MapFocusRequest = {
  nonce: number;
  regionId: string;
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

const MAP_WIDTH = 1000;
const MAP_HEIGHT = 560;
const WORLD_MAP_REFRESH_INTERVAL_MS = 30_000;
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

export default function WorldMapPage() {
  const { lang, text } = useI18n();
  const [snapshot, setSnapshot] = useState<WorldMapSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [commodity, setCommodity] = useState<CommodityFilter>("all");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [riskDeltas, setRiskDeltas] = useState<Record<string, number>>({});
  const [visibleLayers, setVisibleLayers] = useState<VisibleMapLayers>(DEFAULT_MAP_LAYERS);
  const [rendererMode, setRendererMode] = useState<WorldMapRendererMode>("svg");
  const [focusRequest, setFocusRequest] = useState<MapFocusRequest | null>(null);
  const snapshotRef = useRef<WorldMapSnapshot | null>(null);
  const riskScoresRef = useRef<Record<string, number>>({});
  const mountedRef = useRef(false);
  const refreshInFlightRef = useRef(false);

  const loadSnapshot = useCallback(async () => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    setIsRefreshing(true);
    try {
      const next = await fetchWorldMapSnapshot();
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
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void loadSnapshot();
    return () => {
      mountedRef.current = false;
    };
  }, [loadSnapshot]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = window.setInterval(() => {
      void loadSnapshot();
    }, WORLD_MAP_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadSnapshot]);

  const regions = snapshot?.regions ?? [];
  const commodities = useMemo(
    () => Array.from(new Set(regions.map((region) => commodityLabel(region, lang)))),
    [lang, regions]
  );
  const filteredRegions = useMemo(
    () =>
      commodity === "all"
        ? regions
        : regions.filter((region) => commodityLabel(region, lang) === commodity),
    [commodity, lang, regions]
  );
  const indexedRegions = useMemo(
    () =>
      [...filteredRegions]
        .sort((left, right) => right.riskScore - left.riskScore)
        .slice(0, 5),
    [filteredRegions]
  );
  const selectedRegion = regions.find((region) => region.id === selectedId) ?? null;
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
        <div className="absolute left-3 right-3 top-3 z-20 grid gap-2 lg:left-4 lg:right-4 lg:top-4 xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)_auto] xl:items-start">
          <div className="rounded-sm border border-border-subtle bg-black/70 px-3 py-2 shadow-data-panel backdrop-blur-xl">
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
              <DataSourceBadge state={source} compact />
            </div>
            <StatusStrip snapshot={snapshot} source={source} lastUpdatedAt={lastUpdatedAt} />
          </div>

          <div className="min-w-0 max-w-full rounded-sm border border-border-subtle bg-black/68 p-1 shadow-data-panel backdrop-blur-xl xl:justify-self-center">
            <CommodityToggle
              value={commodity}
              options={commodities}
              onChange={(value) => {
                setCommodity(value);
                setSelectedId(null);
                setDetailOpen(false);
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-sm border border-border-subtle bg-black/68 p-1.5 shadow-data-panel backdrop-blur-xl xl:justify-self-end">
            <LayerLegend layers={snapshot?.layers ?? []} />
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

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_48%_38%,rgba(6,182,212,0.18),transparent_30%),radial-gradient(circle_at_80%_65%,rgba(16,185,129,0.13),transparent_24%),linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))]" />
        <div className="pointer-events-none absolute inset-0 z-10 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,0.45)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.45)_1px,transparent_1px)] [background-size:48px_48px]" />
        <WorldMapCanvas
          regions={filteredRegions}
          riskDeltas={riskDeltas}
          selectedId={selectedRegion?.id ?? null}
          visibleLayers={visibleLayers}
          rendererMode={rendererMode}
          focusRequest={focusRequest}
          onSelect={selectRegion}
        />

        <RiskRegionIndex
          regions={indexedRegions}
          selectedId={selectedRegion?.id ?? null}
          onSelect={selectRegion}
        />

        {source === "fallback" && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/65">
            <div className="rounded-sm border border-border-default bg-bg-surface px-5 py-4 text-sm text-text-secondary shadow-data-panel">
              {text("世界风险地图接口暂不可用")}
            </div>
          </div>
        )}
      </Card>

      {detailOpen && selectedRegion && (
        <RegionInsightModal region={selectedRegion} onClose={() => setDetailOpen(false)} />
      )}
    </div>
  );
}

function StatusStrip({
  snapshot,
  source,
  lastUpdatedAt,
}: {
  snapshot: WorldMapSnapshot | null;
  source: DataSourceState;
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
      <div className="flex min-w-0 items-center justify-between gap-2 rounded-xs border border-border-subtle bg-black/38 px-2 py-1.5">
        <span className="text-[10px] text-text-muted">{text("更新")}</span>
        <span className="flex items-center gap-2 font-mono text-xs text-text-primary">
          <DataSourceBadge state={source} compact />
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
    <div className="inline-flex h-7 items-center gap-2 rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-2 text-caption text-brand-emerald-bright">
      <span className={cn("h-1.5 w-1.5 rounded-full bg-brand-emerald-bright", autoRefresh && "animate-heartbeat")} />
      <span>{isRefreshing ? text("同步中") : autoRefresh ? text("实时轮询") : text("手动刷新")}</span>
      {lastUpdatedAt && <span className="font-mono text-text-muted">{formatUpdateTime(lastUpdatedAt)}</span>}
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
    <div className="flex min-w-0 items-center justify-between gap-2 rounded-xs border border-border-subtle bg-black/38 px-2 py-1.5">
      <span className="flex min-w-0 items-center gap-1.5 truncate text-[10px] text-text-muted">
        <Icon className="h-3 w-3 shrink-0" />
        {label}
      </span>
      <span className="font-mono text-xs text-text-primary">{value}</span>
    </div>
  );
}

function CommodityToggle({
  value,
  options,
  onChange,
}: {
  value: CommodityFilter;
  options: string[];
  onChange: (value: CommodityFilter) => void;
}) {
  const { text } = useI18n();
  return (
    <div className="flex max-w-full gap-1 overflow-x-auto">
      {["all", ...options].map((option) => {
        const active = value === option;
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={cn(
              "h-8 shrink-0 rounded-xs px-3 text-xs font-semibold transition-colors",
              active
                ? "bg-brand-emerald text-black"
                : "text-text-muted hover:bg-bg-surface-raised hover:text-text-primary"
            )}
          >
            {option === "all" ? text("全部") : option}
          </button>
        );
      })}
    </div>
  );
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
            {text(label)}
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
            {text(option.label)}
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
      className="absolute bottom-4 left-4 z-20 w-[min(440px,calc(100%-112px))] rounded-sm border border-border-subtle bg-black/70 shadow-data-panel backdrop-blur-xl"
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
      <div className="grid max-h-[238px] gap-1 overflow-y-auto p-2 sm:grid-cols-2">
        {regions.length === 0 && (
          <div className="col-span-full rounded-xs border border-border-subtle bg-black/28 px-3 py-2 text-caption text-text-muted">
            {text("暂无区域")}
          </div>
        )}
        {regions.map((region, index) => {
          const active = region.id === selectedId;
          const color = riskColor(region.riskLevel);
          return (
            <button
              key={region.id}
              type="button"
              data-testid={`world-map-region-index-item-${region.id}`}
              onClick={() => onSelect(region.id)}
              className={cn(
                "group min-w-0 rounded-xs border bg-black/32 px-2.5 py-2 text-left transition-colors",
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
                <span className="font-mono text-xs" style={{ color: color.text }}>
                  {region.riskScore}
                </span>
              </div>
              <div className="mt-1 truncate text-[10px] text-text-muted">
                {(lang === "zh" ? region.story.triggerZh : region.story.triggerEn)} · {region.symbols.join("/")}
              </div>
            </button>
          );
        })}
      </div>
      <div className="border-t border-border-subtle px-3 py-2 text-caption text-text-muted">
        {text("点击区域查看动态风险链")}
      </div>
    </div>
  );
}

function WorldMapCanvas({
  regions,
  riskDeltas,
  selectedId,
  visibleLayers,
  rendererMode,
  focusRequest,
  onSelect,
}: {
  regions: WorldMapRegion[];
  riskDeltas: Record<string, number>;
  selectedId: string | null;
  visibleLayers: VisibleMapLayers;
  rendererMode: WorldMapRendererMode;
  focusRequest: MapFocusRequest | null;
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
  const riskRoutes = useMemo(() => buildRiskRoutes(regions), [regions]);
  const densityCells = useMemo(() => buildRiskDensityCells(regions, projection), [projection, regions]);

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
        className={cn("h-full w-full touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")}
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
            const color = riskColor(region.riskLevel);
            const radius = 22 + region.riskScore * 0.42;
            const delta = riskDeltas[region.id] ?? 0;
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
                {visibleLayers.labels && (
                  <foreignObject x={center.x + 12} y={center.y - 22} width="152" height="54">
                    <div className="rounded-sm border border-border-subtle bg-black/78 px-2 py-1.5 shadow-data-panel backdrop-blur-md">
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate text-[11px] font-semibold text-text-primary">
                          {lang === "zh" ? region.nameZh : region.nameEn}
                        </div>
                        <div className="font-mono text-[11px]" style={{ color: color.text }}>
                          {region.riskScore}
                        </div>
                      </div>
                      <div className="mt-0.5 flex items-center gap-1 truncate text-[10px] text-text-muted">
                        {(lang === "zh" ? region.story.triggerZh : region.story.triggerEn)} ·{" "}
                        {region.symbols.join("/")}
                        {delta !== 0 && (
                          <span className={cn("font-mono", delta > 0 ? "text-data-down" : "text-data-up")}>
                            {delta > 0 ? "+" : ""}
                            {delta}
                          </span>
                        )}
                      </div>
                    </div>
                  </foreignObject>
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
      {rendererMode === "webgl-ready" && (
        <WebGlReadinessPanel
          densityCellCount={densityCells.length}
          regionCount={regions.length}
          routeCount={riskRoutes.length}
        />
      )}
    </div>
  );
}

function WebGlReadinessPanel({
  densityCellCount,
  regionCount,
  routeCount,
}: {
  densityCellCount: number;
  regionCount: number;
  routeCount: number;
}) {
  const { text } = useI18n();
  const rows = [
    { label: "GeoJson区域", value: regionCount, status: "ready" },
    { label: "Heatmap密度", value: densityCellCount, status: "ready" },
    { label: "Arc飞线", value: routeCount, status: "ready" },
    { label: "Tile天气", value: text("待接入"), status: "planned" },
  ];
  return (
    <div
      data-testid="world-map-webgl-readiness"
      className="pointer-events-none absolute right-4 top-[118px] z-20 hidden w-[260px] rounded-sm border border-brand-emerald/25 bg-black/72 p-3 shadow-data-panel backdrop-blur-xl xl:block"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <Sparkles className="h-4 w-4 text-brand-emerald-bright" />
            {text("WebGL 预备")}
          </div>
          <p className="mt-1 text-caption leading-4 text-text-muted">
            {text("当前仍由 SVG 承载交互，GPU 图层按 deck.gl 口径组织")}
          </p>
        </div>
        <span className="rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-2 py-0.5 font-mono text-caption text-brand-emerald-bright">
          B.2
        </span>
      </div>
      <div className="mt-3 grid gap-1.5">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between gap-3 rounded-xs border border-border-subtle bg-black/35 px-2 py-1.5"
          >
            <span className="text-caption text-text-secondary">{text(row.label)}</span>
            <span
              className={cn(
                "font-mono text-caption",
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
      className="absolute bottom-4 right-4 z-20 flex items-center gap-1 rounded-sm border border-border-subtle bg-black/72 p-1 shadow-data-panel backdrop-blur-md"
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

function RegionInsightModal({ region, onClose }: { region: WorldMapRegion; onClose: () => void }) {
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
    <div className="fixed inset-0 z-[80] overflow-hidden">
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
        className="absolute bottom-3 left-3 right-3 max-h-[86vh] overflow-hidden rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(18,20,19,0.96),rgba(3,5,4,0.98))] shadow-[0_28px_90px_rgba(0,0,0,0.58),inset_1px_0_0_rgba(255,255,255,0.05)] backdrop-blur-2xl md:bottom-3 md:left-auto md:right-3 md:top-3 md:max-h-none md:w-[min(520px,calc(100vw-112px))]"
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
              <div className="rounded-sm border border-border-subtle bg-black/42 p-4">
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

            <Link
              href={region.causalScope.causalWebUrl}
              className="flex h-10 items-center justify-center gap-2 rounded-sm border border-brand-cyan/35 bg-brand-cyan/10 text-sm font-semibold text-brand-cyan hover:bg-brand-cyan/15"
            >
              <Link2 className="h-4 w-4" />
              {region.causalScope.hasDirectLinks
                ? text("打开关联因果网络")
                : text("打开同商品因果网络")}
            </Link>

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
  return (
    <div className="grid grid-cols-2 gap-2">
      <RuntimePill icon={AlertTriangle} label={text("预警")} value={region.runtime.alerts} />
      <RuntimePill icon={DatabaseZap} label={text("新闻")} value={region.runtime.newsEvents} />
      <RuntimePill icon={Activity} label={text("信号")} value={region.runtime.signals} />
      <RuntimePill icon={ShieldAlert} label={text("持仓")} value={region.runtime.positions} />
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
    <section className={cn("rounded-sm border border-border-subtle bg-bg-base p-4", compact && "h-full")}>
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
    <div className="rounded-sm border border-border-subtle bg-black/35 p-3">
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
          className="relative grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-sm border border-border-subtle bg-black/35 p-3"
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
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={`${row.source}-${row.titleZh}`} className="rounded-xs border border-border-subtle bg-black/30 px-3 py-2">
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
    <div className="rounded-sm border border-border-subtle bg-black/35 px-3 py-2">
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

function buildRiskDensityCells(regions: WorldMapRegion[], projection: GeoProjection): RiskDensityCell[] {
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
    .slice(0, 180);
}

function buildRiskRoutes(regions: WorldMapRegion[]) {
  const routes: Array<{ id: string; from: GeoPoint; to: GeoPoint; weight: number }> = [];

  for (let index = 0; index < regions.length; index += 1) {
    for (let nextIndex = index + 1; nextIndex < regions.length; nextIndex += 1) {
      const source = regions[index];
      const target = regions[nextIndex];
      const sharedSymbols = source.symbols.filter((symbol) => target.symbols.includes(symbol));
      const sharedCommodity =
        source.commodityZh === target.commodityZh || source.commodityEn === target.commodityEn;
      if (sharedSymbols.length === 0 && !sharedCommodity) continue;

      routes.push({
        id: `${source.id}-${target.id}`,
        from: source.center,
        to: target.center,
        weight: Math.min(1, (source.riskScore + target.riskScore) / 200 + sharedSymbols.length * 0.1),
      });
    }
  }

  return routes.sort((a, b) => b.weight - a.weight).slice(0, 10);
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

function commodityLabel(region: WorldMapRegion, lang: "zh" | "en"): string {
  return lang === "zh" ? region.commodityZh : region.commodityEn;
}
