"use client";

import Link from "next/link";
import type { ComponentType } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CloudRain,
  DatabaseZap,
  Globe2,
  Layers3,
  Link2,
  RefreshCw,
  Satellite,
  ShieldAlert,
  Waves,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { MetricTile } from "@/components/MetricTile";
import {
  fetchWorldMapSnapshot,
  type GeoPoint,
  type WorldMapLayer,
  type WorldMapRegion,
  type WorldMapSnapshot,
  type WorldRiskLevel,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type CommodityFilter = "all" | string;

const MAP_WIDTH = 1000;
const MAP_HEIGHT = 520;

const LAND_PATHS = [
  "M105 143 C146 88 235 82 287 126 C319 154 331 210 299 249 C253 303 148 281 104 235 C76 206 73 174 105 143Z",
  "M238 287 C286 271 347 297 368 352 C387 400 355 462 295 468 C234 474 186 428 188 369 C190 331 207 302 238 287Z",
  "M458 126 C525 83 627 93 675 153 C720 210 695 280 631 304 C562 329 481 299 444 241 C413 192 420 151 458 126Z",
  "M582 307 C642 300 708 341 722 403 C733 454 689 498 629 492 C578 487 543 447 547 394 C550 350 561 321 582 307Z",
  "M706 180 C764 122 861 132 914 192 C959 243 942 316 884 344 C815 377 720 344 687 276 C670 242 676 210 706 180Z",
  "M771 379 C818 351 898 370 922 423 C944 472 902 511 838 501 C786 493 752 451 760 410 C763 397 767 386 771 379Z",
];

export default function WorldMapPage() {
  const { lang, text } = useI18n();
  const [snapshot, setSnapshot] = useState<WorldMapSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [commodity, setCommodity] = useState<CommodityFilter>("all");

  useEffect(() => {
    let mounted = true;
    fetchWorldMapSnapshot()
      .then((next) => {
        if (!mounted) return;
        setSnapshot(next);
        setSource(next.summary.runtimeLinkedRegions > 0 ? "api" : "partial");
        setSelectedId(next.regions[0]?.id ?? null);
      })
      .catch(() => {
        if (!mounted) return;
        setSnapshot(null);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

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
  const selectedRegion =
    filteredRegions.find((region) => region.id === selectedId) ??
    filteredRegions[0] ??
    regions[0] ??
    null;

  return (
    <div className="min-h-full space-y-5 px-4 py-4 animate-fade-in sm:px-6 lg:px-8">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("世界风险地图")}</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {text("地理空间预警、天气异常与因果链路作用域")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CommodityToggle
            value={commodity}
            options={commodities}
            onChange={(value) => {
              setCommodity(value);
              setSelectedId(null);
            }}
          />
          <DataSourceBadge state={source} />
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            <RefreshCw className="h-4 w-4" />
            {text("刷新")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <MetricTile
          label={text("覆盖区域")}
          value={String(snapshot?.summary.regions ?? 0)}
          caption={text("产区与链路")}
          icon={Globe2}
          tone="cyan"
        />
        <MetricTile
          label={text("升温区域")}
          value={String(snapshot?.summary.elevatedRegions ?? 0)}
          caption={text("风险分 ≥ 55")}
          icon={ShieldAlert}
          tone="warning"
        />
        <MetricTile
          label={text("最高风险")}
          value={String(snapshot?.summary.maxRiskScore ?? 0)}
          caption={text("综合评分")}
          icon={Activity}
          tone={(snapshot?.summary.maxRiskScore ?? 0) >= 72 ? "warning" : "up"}
        />
        <MetricTile
          label={text("因果联动")}
          value={String(snapshot?.summary.runtimeLinkedRegions ?? 0)}
          caption={text("真实运行态关联")}
          icon={Link2}
          tone="up"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card variant="flat" className="overflow-hidden p-0">
          <CardHeader className="border-b border-border-subtle px-4 py-3">
            <div>
              <CardTitle>{text("全球风险地理层")}</CardTitle>
              <CardSubtitle>{text("天气 baseline + 运行态预警 / 新闻 / 信号 / 持仓")}</CardSubtitle>
            </div>
            <LayerLegend layers={snapshot?.layers ?? []} />
          </CardHeader>
          <div className="relative min-h-[620px] overflow-hidden bg-[radial-gradient(circle_at_50%_30%,rgba(6,182,212,0.12),transparent_28%),linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))]">
            <WorldMapCanvas
              regions={filteredRegions}
              selectedId={selectedRegion?.id ?? null}
              onSelect={setSelectedId}
            />
            {source === "fallback" && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/65">
                <div className="rounded-sm border border-border-default bg-bg-surface px-5 py-4 text-sm text-text-secondary shadow-data-panel">
                  {text("世界风险地图接口暂不可用")}
                </div>
              </div>
            )}
          </div>
        </Card>

        <RegionDetail region={selectedRegion} source={source} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {filteredRegions.slice(0, 3).map((region) => (
          <RegionStripCard key={region.id} region={region} onSelect={() => setSelectedId(region.id)} />
        ))}
      </div>
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
    <div className="flex max-w-full gap-1 overflow-x-auto rounded-sm border border-border-subtle bg-bg-base p-1">
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
    <div className="hidden flex-wrap items-center gap-2 lg:flex">
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

function WorldMapCanvas({
  regions,
  selectedId,
  onSelect,
}: {
  regions: WorldMapRegion[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { lang } = useI18n();
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img">
      <defs>
        <linearGradient id="oceanLine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgba(6,182,212,0.35)" />
          <stop offset="100%" stopColor="rgba(16,185,129,0.18)" />
        </linearGradient>
        <filter id="riskGlow">
          <feGaussianBlur stdDeviation="9" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {Array.from({ length: 9 }).map((_, index) => (
        <line
          key={`lat-${index}`}
          x1="0"
          x2={MAP_WIDTH}
          y1={60 + index * 50}
          y2={60 + index * 50}
          stroke="rgba(148,163,184,0.08)"
          strokeWidth="1"
        />
      ))}
      {Array.from({ length: 12 }).map((_, index) => (
        <line
          key={`lon-${index}`}
          x1={70 + index * 80}
          x2={70 + index * 80}
          y1="0"
          y2={MAP_HEIGHT}
          stroke="rgba(148,163,184,0.06)"
          strokeWidth="1"
        />
      ))}

      {LAND_PATHS.map((path, index) => (
        <path
          key={index}
          d={path}
          fill="rgba(15,23,42,0.38)"
          stroke="url(#oceanLine)"
          strokeWidth="1"
        />
      ))}

      {regions.map((region) => {
        const center = project(region.center);
        const selected = region.id === selectedId;
        const color = riskColor(region.riskLevel);
        const radius = 34 + region.riskScore * 0.35;
        return (
          <g
            key={region.id}
            role="button"
            tabIndex={0}
            className="cursor-pointer outline-none"
            onClick={() => onSelect(region.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") onSelect(region.id);
            }}
          >
            <path
              d={polygonPath(region.polygon)}
              fill={color.fill}
              stroke={selected ? color.strokeStrong : color.stroke}
              strokeWidth={selected ? 2.4 : 1.2}
              filter={selected ? "url(#riskGlow)" : undefined}
            />
            <circle
              cx={center.x}
              cy={center.y}
              r={radius}
              fill="none"
              stroke={color.stroke}
              strokeWidth="1.5"
              strokeDasharray="3 7"
              opacity={selected ? 0.9 : 0.45}
            />
            <circle cx={center.x} cy={center.y} r={7} fill={color.strokeStrong} filter="url(#riskGlow)" />
            <foreignObject x={center.x + 12} y={center.y - 24} width="178" height="74">
              <div
                className={cn(
                  "rounded-sm border bg-black/70 px-2.5 py-2 shadow-data-panel backdrop-blur-md",
                  selected ? "border-brand-cyan text-text-primary" : "border-border-subtle text-text-secondary"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate text-xs font-semibold">
                    {lang === "zh" ? region.nameZh : region.nameEn}
                  </div>
                  <div className="font-mono text-[11px]" style={{ color: color.text }}>
                    {region.riskScore}
                  </div>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-[10px] text-text-muted">
                  <span>{lang === "zh" ? region.commodityZh : region.commodityEn}</span>
                  <span>·</span>
                  <span>{region.symbols.join("/")}</span>
                </div>
              </div>
            </foreignObject>
          </g>
        );
      })}
    </svg>
  );
}

function RegionDetail({ region, source }: { region: WorldMapRegion | null; source: DataSourceState }) {
  const { lang, text } = useI18n();
  if (!region) {
    return (
      <Card variant="data" className="min-h-[420px] py-16 text-center text-sm text-text-secondary">
        {text(source === "loading" ? "世界风险地图加载中" : "当前暂无区域风险数据")}
      </Card>
    );
  }
  const color = riskColor(region.riskLevel);
  return (
    <Card variant="data" className="flex min-h-[620px] flex-col">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Satellite className="h-4 w-4 text-brand-cyan" />
            <h2 className="text-h2 text-text-primary">{lang === "zh" ? region.nameZh : region.nameEn}</h2>
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            {lang === "zh" ? region.narrativeZh : region.narrativeEn}
          </p>
        </div>
        <Badge variant={region.riskScore >= 72 ? "high" : region.riskScore >= 55 ? "medium" : "low"}>
          {text(riskLabel(region.riskLevel))}
        </Badge>
      </div>

      <div className="mt-5 rounded-sm border border-border-subtle bg-bg-base p-4">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-caption text-text-muted">{text("区域综合风险")}</div>
            <div className="mt-1 font-mono text-4xl font-semibold" style={{ color: color.text }}>
              {region.riskScore}
            </div>
          </div>
          <div className="text-right text-caption text-text-muted">
            <div>{region.symbols.join(" / ")}</div>
            <div className="mt-1">{text(dataQualityLabel(region.dataQuality))}</div>
          </div>
        </div>
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-bg-surface-raised">
          <div className="h-full rounded-full" style={{ width: `${region.riskScore}%`, background: color.text }} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <RuntimePill icon={AlertTriangle} label={text("预警")} value={region.runtime.alerts} />
        <RuntimePill icon={DatabaseZap} label={text("新闻")} value={region.runtime.newsEvents} />
        <RuntimePill icon={Activity} label={text("信号")} value={region.runtime.signals} />
        <RuntimePill icon={ShieldAlert} label={text("持仓")} value={region.runtime.positions} />
      </div>

      <div className="mt-5 space-y-3">
        <SectionTitle icon={CloudRain} label={text("天气异常")} />
        <WeatherMetric
          label={text("降水距平")}
          value={`${region.weather.precipitationAnomalyPct >= 0 ? "+" : ""}${region.weather.precipitationAnomalyPct.toFixed(1)}%`}
          tone={region.weather.precipitationAnomalyPct >= 0 ? "up" : "down"}
        />
        <WeatherMetric label={text("7日降水")} value={`${region.weather.rainfall7dMm.toFixed(0)} mm`} tone="neutral" />
        <WeatherMetric
          label={text("洪涝风险")}
          value={`${Math.round(region.weather.floodRisk * 100)}%`}
          tone={region.weather.floodRisk > 0.55 ? "warning" : "neutral"}
        />
        <div className="text-caption text-text-muted">
          {text("数据源")}：{region.weather.dataSource}
        </div>
      </div>

      <div className="mt-5 space-y-3">
        <SectionTitle icon={Waves} label={text("主要驱动")} />
        {region.drivers.map((driver) => (
          <div key={driver.labelZh} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-text-secondary">{lang === "zh" ? driver.labelZh : driver.labelEn}</span>
              <span className="font-mono text-text-muted">{Math.round(driver.weight * 100)}%</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-bg-surface-raised">
              <div className="h-full rounded-full bg-brand-emerald" style={{ width: `${driver.weight * 100}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-auto pt-5">
        {region.causalScope.hasDirectLinks ? (
          <Link
            href={region.causalScope.causalWebUrl}
            className="flex h-10 items-center justify-center gap-2 rounded-sm border border-brand-cyan/35 bg-brand-cyan/10 text-sm font-semibold text-brand-cyan hover:bg-brand-cyan/15"
          >
            <Link2 className="h-4 w-4" />
            {text("打开关联因果网络")}
          </Link>
        ) : (
          <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-3 text-sm text-text-secondary">
            {text("当前区域暂无直接因果联动")}
          </div>
        )}
      </div>
    </Card>
  );
}

function RegionStripCard({ region, onSelect }: { region: WorldMapRegion; onSelect: () => void }) {
  const { lang, text } = useI18n();
  const color = riskColor(region.riskLevel);
  return (
    <button
      type="button"
      onClick={onSelect}
      className="rounded-sm border border-border-subtle bg-bg-surface p-4 text-left shadow-inner-panel transition-colors hover:border-brand-cyan/40 hover:bg-bg-surface-raised"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-text-primary">
            {lang === "zh" ? region.nameZh : region.nameEn}
          </div>
          <div className="mt-1 text-caption text-text-muted">{region.symbols.join(" / ")}</div>
        </div>
        <div className="font-mono text-lg" style={{ color: color.text }}>
          {region.riskScore}
        </div>
      </div>
      <div className="mt-3 text-xs text-text-secondary">
        {text("预警")} {region.runtime.alerts} · {text("新闻")} {region.runtime.newsEvents} ·{" "}
        {text("信号")} {region.runtime.signals}
      </div>
    </button>
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

function WeatherMetric({ label, value, tone }: { label: string; value: string; tone: "up" | "down" | "warning" | "neutral" }) {
  return (
    <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2">
      <span className="text-sm text-text-secondary">{label}</span>
      <span
        className={cn(
          "font-mono text-sm",
          tone === "up" && "text-data-up",
          tone === "down" && "text-data-down",
          tone === "warning" && "text-brand-orange",
          tone === "neutral" && "text-text-primary"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function SectionTitle({ icon: Icon, label }: { icon: ComponentType<{ className?: string }>; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
      <Icon className="h-4 w-4 text-brand-emerald-bright" />
      {label}
    </div>
  );
}

function project(point: GeoPoint): { x: number; y: number } {
  return {
    x: ((point.lon + 180) / 360) * MAP_WIDTH,
    y: ((90 - point.lat) / 180) * MAP_HEIGHT,
  };
}

function polygonPath(points: GeoPoint[]): string {
  return `${points
    .map((point, index) => {
      const projected = project(point);
      return `${index === 0 ? "M" : "L"}${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`;
    })
    .join(" ")} Z`;
}

function riskColor(level: WorldRiskLevel) {
  switch (level) {
    case "critical":
      return { text: "#ff4d4f", fill: "rgba(255,77,79,0.18)", stroke: "rgba(255,77,79,0.52)", strokeStrong: "#ff4d4f" };
    case "high":
      return { text: "#f97316", fill: "rgba(249,115,22,0.18)", stroke: "rgba(249,115,22,0.5)", strokeStrong: "#f97316" };
    case "elevated":
      return { text: "#f59e0b", fill: "rgba(245,158,11,0.16)", stroke: "rgba(245,158,11,0.45)", strokeStrong: "#f59e0b" };
    case "watch":
      return { text: "#22d3ee", fill: "rgba(34,211,238,0.13)", stroke: "rgba(34,211,238,0.42)", strokeStrong: "#22d3ee" };
    default:
      return { text: "#10b981", fill: "rgba(16,185,129,0.11)", stroke: "rgba(16,185,129,0.35)", strokeStrong: "#10b981" };
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

function dataQualityLabel(quality: WorldMapRegion["dataQuality"]): string {
  if (quality === "runtime") return "运行态数据";
  if (quality === "partial") return "部分数据";
  return "基线数据";
}

function commodityLabel(region: WorldMapRegion, lang: "zh" | "en"): string {
  return lang === "zh" ? region.commodityZh : region.commodityEn;
}
