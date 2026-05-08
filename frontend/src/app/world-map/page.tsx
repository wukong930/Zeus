"use client";

import Link from "next/link";
import type { ComponentType, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
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
  RefreshCw,
  Route,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
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

const MAP_WIDTH = 1000;
const MAP_HEIGHT = 560;

const LAND_PATHS = [
  "M105 143 C146 88 235 82 287 126 C319 154 331 210 299 249 C253 303 148 281 104 235 C76 206 73 174 105 143Z",
  "M238 306 C286 290 347 316 368 371 C387 419 355 481 295 487 C234 493 186 447 188 388 C190 350 207 321 238 306Z",
  "M458 126 C525 83 627 93 675 153 C720 210 695 280 631 304 C562 329 481 299 444 241 C413 192 420 151 458 126Z",
  "M582 326 C642 319 708 360 722 422 C733 473 689 517 629 511 C578 506 543 466 547 413 C550 369 561 340 582 326Z",
  "M706 180 C764 122 861 132 914 192 C959 243 942 316 884 344 C815 377 720 344 687 276 C670 242 676 210 706 180Z",
  "M771 398 C818 370 898 389 922 442 C944 491 902 530 838 520 C786 512 752 470 760 429 C763 416 767 405 771 398Z",
];

export default function WorldMapPage() {
  const { lang, text } = useI18n();
  const [snapshot, setSnapshot] = useState<WorldMapSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [commodity, setCommodity] = useState<CommodityFilter>("all");

  useEffect(() => {
    let mounted = true;
    fetchWorldMapSnapshot()
      .then((next) => {
        if (!mounted) return;
        setSnapshot(next);
        setSource(next.summary.runtimeLinkedRegions > 0 ? "api" : "partial");
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
  const selectedRegion = regions.find((region) => region.id === selectedId) ?? null;

  return (
    <div className="flex min-h-full flex-col gap-3 px-4 py-3 animate-fade-in sm:px-6 lg:px-8">
      <header className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("世界风险地图")}</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {text("按商品属性自适应解释天气、物流、供应和价格传导")}
          </p>
        </div>
        <StatusStrip snapshot={snapshot} source={source} />
      </header>

      <Card variant="flat" className="relative min-h-[740px] flex-1 overflow-hidden p-0">
        <div className="absolute left-4 right-4 top-4 z-20 flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-full rounded-sm border border-border-subtle bg-black/72 p-1 shadow-data-panel backdrop-blur-md">
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
          <div className="flex flex-wrap items-center gap-2 rounded-sm border border-border-subtle bg-black/72 p-1.5 shadow-data-panel backdrop-blur-md">
            <LayerLegend layers={snapshot?.layers ?? []} />
            <DataSourceBadge state={source} />
            <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
              <RefreshCw className="h-4 w-4" />
              {text("刷新")}
            </Button>
          </div>
        </div>

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_48%_38%,rgba(6,182,212,0.16),transparent_28%),radial-gradient(circle_at_80%_65%,rgba(16,185,129,0.12),transparent_22%),linear-gradient(180deg,rgba(5,7,6,0.98),rgba(0,0,0,1))]" />
        <WorldMapCanvas
          regions={filteredRegions}
          selectedId={selectedRegion?.id ?? null}
          onSelect={(id) => {
            setSelectedId(id);
            setDetailOpen(true);
          }}
        />

        <div className="absolute bottom-4 left-4 z-20 max-w-[520px] rounded-sm border border-border-subtle bg-black/72 px-4 py-3 text-sm text-text-secondary shadow-data-panel backdrop-blur-md">
          <div className="flex items-center gap-2 text-text-primary">
            <Compass className="h-4 w-4 text-brand-cyan" />
            {text("点击区域查看动态风险链")}
          </div>
          <p className="mt-1 text-caption text-text-muted">
            {text("传导链由商品属性、天气 baseline、运行态预警、新闻、信号和持仓共同生成。")}
          </p>
        </div>

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
}: {
  snapshot: WorldMapSnapshot | null;
  source: DataSourceState;
}) {
  const { text } = useI18n();
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:min-w-[640px]">
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
      <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2">
        <span className="text-caption text-text-muted">{text("数据")}</span>
        <DataSourceBadge state={source} compact />
      </div>
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
    <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2">
      <span className="flex items-center gap-1.5 text-caption text-text-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
      <span className="font-mono text-sm text-text-primary">{value}</span>
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
        <linearGradient id="worldMapOceanLine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgba(6,182,212,0.35)" />
          <stop offset="100%" stopColor="rgba(16,185,129,0.18)" />
        </linearGradient>
        <filter id="worldMapRiskGlow">
          <feGaussianBlur stdDeviation="10" result="blur" />
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
          y1={80 + index * 48}
          y2={80 + index * 48}
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
          stroke="url(#worldMapOceanLine)"
          strokeWidth="1"
        />
      ))}

      {regions.map((region) => {
        const center = project(region.center);
        const selected = region.id === selectedId;
        const color = riskColor(region.riskLevel);
        const radius = 44 + region.riskScore * 0.55;
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
              strokeWidth={selected ? 2.8 : 1.2}
              filter={selected ? "url(#worldMapRiskGlow)" : undefined}
            />
            <circle
              cx={center.x}
              cy={center.y}
              r={radius}
              fill="none"
              stroke={color.stroke}
              strokeWidth="1.5"
              strokeDasharray="3 8"
              opacity={selected ? 0.88 : 0.38}
            />
            <circle cx={center.x} cy={center.y} r={8} fill={color.strokeStrong} filter="url(#worldMapRiskGlow)" />
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
                <div className="mt-0.5 truncate text-[10px] text-text-muted">
                  {(lang === "zh" ? region.story.triggerZh : region.story.triggerEn)} ·{" "}
                  {region.symbols.join("/")}
                </div>
              </div>
            </foreignObject>
          </g>
        );
      })}
    </svg>
  );
}

function RegionInsightModal({ region, onClose }: { region: WorldMapRegion; onClose: () => void }) {
  const { lang, text } = useI18n();
  const color = riskColor(region.riskLevel);
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/78 px-4 py-6 backdrop-blur-sm">
      <div className="max-h-[92vh] w-[min(980px,calc(100vw-32px))] overflow-hidden rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(18,20,19,0.98),rgba(3,5,4,0.99))] shadow-data-panel">
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Route className="h-4 w-4 text-brand-cyan" />
              <h2 className="text-h2 text-text-primary">
                {lang === "zh" ? region.story.headlineZh : region.story.headlineEn}
              </h2>
              <Badge variant={region.riskScore >= 72 ? "high" : region.riskScore >= 55 ? "medium" : "low"}>
                {text(riskLabel(region.riskLevel))}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm text-text-secondary">
              {lang === "zh" ? region.narrativeZh : region.narrativeEn}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xs border border-border-subtle bg-bg-base text-text-muted hover:text-text-primary"
            aria-label={text("关闭")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[calc(92vh-88px)] overflow-y-auto p-5">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
            <div className="space-y-3">
              <div className="rounded-sm border border-border-subtle bg-bg-base p-4">
                <div className="text-caption text-text-muted">{text("区域综合风险")}</div>
                <div className="mt-1 font-mono text-5xl font-semibold" style={{ color: color.text }}>
                  {region.riskScore}
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-bg-surface-raised">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${region.riskScore}%`, background: color.text }}
                  />
                </div>
              </div>
              <RuntimeGrid region={region} />
              <Link
                href={region.causalScope.causalWebUrl}
                className="flex h-10 items-center justify-center gap-2 rounded-sm border border-brand-cyan/35 bg-brand-cyan/10 text-sm font-semibold text-brand-cyan hover:bg-brand-cyan/15"
              >
                <Link2 className="h-4 w-4" />
                {region.causalScope.hasDirectLinks
                  ? text("打开关联因果网络")
                  : text("打开同商品因果网络")}
              </Link>
            </div>

            <div className="space-y-4">
              <InsightSection icon={Sparkles} title={text("动态预警")}>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {region.adaptiveAlerts.map((alert) => (
                    <AdaptiveAlertCard key={alert.id} alert={alert} />
                  ))}
                </div>
              </InsightSection>

              <InsightSection icon={Route} title={text("商品传导链")}>
                <StoryChain steps={region.story.chain} />
              </InsightSection>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <InsightSection icon={ListChecks} title={text("证据")} compact>
                  <EvidenceList region={region} kind="evidence" />
                </InsightSection>
                <InsightSection icon={AlertTriangle} title={text("反证")} compact>
                  <EvidenceList region={region} kind="counterEvidence" />
                </InsightSection>
              </div>

              <InsightSection icon={CloudRain} title={text("天气异常")}>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
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
        </div>
      </div>
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
    <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
      {steps.map((step, index) => (
        <div key={`${step.stage}-${index}`} className="relative rounded-sm border border-border-subtle bg-black/35 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-caption text-brand-cyan">{text(stageLabel(step.stage))}</span>
            <span className="font-mono text-caption text-text-muted">
              {Math.round(step.confidence * 100)}%
            </span>
          </div>
          <div className="text-sm text-text-primary">{lang === "zh" ? step.labelZh : step.labelEn}</div>
          {index < steps.length - 1 && (
            <div className="pointer-events-none absolute -right-2 top-1/2 hidden h-px w-4 bg-brand-cyan/45 md:block" />
          )}
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
