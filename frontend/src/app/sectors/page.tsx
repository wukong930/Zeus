"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { DataSourceBadge } from "@/components/DataSourceBadge";
import type { DataSourceState } from "@/components/DataSourceBadge";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import { Badge } from "@/components/Badge";
import { MetricTile } from "@/components/MetricTile";
import { SECTORS } from "@/data/sectorUniverse";
import type { SectorData } from "@/lib/domain";
import { fetchSectorSnapshot } from "@/lib/api";
import { cn, formatPercent } from "@/lib/utils";
import { Activity, Gauge, Layers3, RadioTower } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useEffect, useMemo, useState } from "react";

export default function SectorsPage() {
  const { text } = useI18n();
  const [sectors, setSectors] = useState<SectorData[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [unavailableSections, setUnavailableSections] = useState<string[]>([]);
  const activeSignals = useMemo(
    () => sectors.flatMap((sector) => sector.symbols).filter((symbol) => symbol.signalActive).length,
    [sectors]
  );
  const avgConviction = useMemo(
    () => sectors.reduce((sum, sector) => sum + sector.conviction, 0) / Math.max(sectors.length, 1),
    [sectors]
  );

  useEffect(() => {
    let mounted = true;
    fetchSectorSnapshot(SECTORS)
      .then((snapshot) => {
        if (!mounted) return;
        setSectors(snapshot.sectors);
        setUnavailableSections(snapshot.unavailableSections);
        setSource(snapshot.degraded ? "partial" : "api");
      })
      .catch(() => {
        if (!mounted) return;
        setSectors([]);
        setUnavailableSections([]);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("Sectors")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {text("板块层方向判断 + 各品种活跃度 + conviction 因子")}
          </p>
        </div>
        <DataSourceBadge state={source} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
        <MetricTile label={text("板块数")} value={String(sectors.length)} caption="coverage" icon={Layers3} tone="cyan" />
        <MetricTile label={text("活跃信号")} value={String(activeSignals)} caption="orange pulse" icon={RadioTower} tone="warning" />
        <MetricTile label={text("平均 conviction")} value={`${avgConviction >= 0 ? "+" : ""}${avgConviction.toFixed(2)}`} caption="cross-sector" icon={Gauge} tone={avgConviction >= 0 ? "up" : "down"} />
        <MetricTile label={text("方向状态")} value={text(avgConviction >= 0 ? "Risk-on" : "Defensive")} caption="sector bias" icon={Activity} tone={avgConviction >= 0 ? "up" : "warning"} />
      </div>

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>{text("板块热力图")}</CardTitle>
            <CardSubtitle>{text("橙色脉动 = 信号活跃 · 颜色亮度 = 涨跌幅")}</CardSubtitle>
          </div>
          <DataSourceBadge state={source} compact />
        </CardHeader>
        <SectorHeatmap sectors={sectors} emptyMessage={emptySectorSnapshotMessage(source)} />
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {sectors.length > 0 ? sectors.map((s) => {
          const factors = runtimeFactorsForSector(s, unavailableSections);
          return (
            <Card key={s.id} variant="data" interactive>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <CardTitle>{text(s.name)}</CardTitle>
                  <Badge variant={s.conviction >= 0 ? "up" : "down"}>
                    conviction {s.conviction >= 0 ? "+" : ""}{s.conviction.toFixed(2)}
                  </Badge>
                </div>
              </CardHeader>
              <div className="space-y-2">
                {s.symbols.map((sym) => (
                  <div key={sym.code} className="flex items-center gap-3">
                    <div className="font-mono text-sm w-12">{sym.code}</div>
                    <div className="text-text-secondary text-sm flex-1">{text(sym.name)}</div>
                    {sym.signalActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-brand-orange animate-heartbeat" />
                    )}
                    <div className={cn("font-mono text-sm tabular-nums w-16 text-right", sym.change >= 0 ? "text-data-up" : "text-data-down")}>
                      {sym.change >= 0 ? "+" : ""}{sym.change.toFixed(2)}%
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-border-subtle pt-3 mt-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="text-caption text-text-muted">{text("运行态因子")}</div>
                  {source === "partial" && <Badge variant="orange">{text("部分数据")}</Badge>}
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  {factors.map((factor) => (
                    <RuntimeFactor key={factor.label} factor={factor} />
                  ))}
                </div>
              </div>
            </Card>
          );
        }) : (
          <Card variant="data" className="col-span-2 py-10 text-center text-sm text-text-secondary">
            {text(emptySectorSnapshotMessage(source))}
          </Card>
        )}
      </div>
    </div>
  );
}

function emptySectorSnapshotMessage(source: DataSourceState): string {
  if (source === "loading") return "板块快照加载中";
  if (source === "fallback") return "板块快照接口暂不可用";
  return "当前暂无板块快照";
}

type RuntimeFactor = {
  label: string;
  value: number;
  caption: string;
  tone: "up" | "warning" | "neutral";
};

function RuntimeFactor({ factor }: { factor: RuntimeFactor }) {
  const { text } = useI18n();
  const barClass =
    factor.tone === "up"
      ? "bg-brand-emerald"
      : factor.tone === "warning"
        ? "bg-brand-orange"
        : "bg-text-muted";

  return (
    <div className="rounded-xs border border-border-subtle bg-bg-base p-2 shadow-inner-panel">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-caption text-text-muted">{text(factor.label)}</span>
        <span className="font-mono text-caption text-text-secondary">{factor.caption}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-bg-surface-raised">
        <div className={cn("h-full", barClass)} style={{ width: `${Math.round(factor.value * 100)}%` }} />
      </div>
    </div>
  );
}

function runtimeFactorsForSector(sector: SectorData, unavailableSections: string[]): RuntimeFactor[] {
  const missingMarketSymbols = marketSymbolsFromUnavailableSections(unavailableSections);
  const total = Math.max(sector.symbols.length, 1);
  const availableMarket = sector.symbols.filter((symbol) => !missingMarketSymbols.has(symbol.code)).length;
  const activeSignals = sector.symbols.filter((symbol) => symbol.signalActive).length;
  const avgAbsChange = sector.symbols.reduce((sum, symbol) => sum + Math.abs(symbol.change), 0) / total;
  const nonFlatSymbols = sector.symbols.filter((symbol) => Math.abs(symbol.change) > 0.0001);
  const sectorDirection = Math.sign(sector.symbols.reduce((sum, symbol) => sum + symbol.change, 0));
  const alignedSymbols =
    sectorDirection === 0
      ? 0
      : nonFlatSymbols.filter((symbol) => Math.sign(symbol.change) === sectorDirection).length;
  const consistencyBase = Math.max(nonFlatSymbols.length, 1);

  return [
    {
      label: "行情覆盖",
      value: availableMarket / total,
      caption: `${availableMarket}/${total}`,
      tone: availableMarket === total ? "up" : availableMarket > 0 ? "warning" : "neutral",
    },
    {
      label: "信号活跃",
      value: activeSignals / total,
      caption: `${activeSignals}/${total}`,
      tone: activeSignals > 0 ? "up" : "neutral",
    },
    {
      label: "方向强度",
      value: clamp(avgAbsChange / 2.5, 0, 1),
      caption: formatPercent(avgAbsChange, 2, false),
      tone: avgAbsChange >= 1 ? "up" : avgAbsChange > 0 ? "warning" : "neutral",
    },
    {
      label: "内部一致",
      value: alignedSymbols / consistencyBase,
      caption: `${alignedSymbols}/${consistencyBase}`,
      tone: alignedSymbols / consistencyBase >= 0.7 ? "up" : alignedSymbols > 0 ? "warning" : "neutral",
    },
  ];
}

function marketSymbolsFromUnavailableSections(sections: string[]): Set<string> {
  const symbols = new Set<string>();
  sections.forEach((section) => {
    if (!section.startsWith("market:")) return;
    section
      .slice("market:".length)
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((symbol) => symbols.add(symbol));
  });
  return symbols;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
