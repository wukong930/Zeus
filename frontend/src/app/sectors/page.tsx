"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { DataSourceBadge } from "@/components/DataSourceBadge";
import type { DataSourceState } from "@/components/DataSourceBadge";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import { Badge } from "@/components/Badge";
import { MetricTile } from "@/components/MetricTile";
import { SECTORS } from "@/data/mock";
import { fetchSectorSnapshot } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Activity, Gauge, Layers3, RadioTower } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useEffect, useMemo, useState } from "react";

const FACTORS = ["成本", "库存", "季节", "利润"] as const;

function factorValue(sectorId: string, factorIndex: number) {
  const seed = [...sectorId].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return 0.32 + (((seed * (factorIndex + 3)) % 52) / 100);
}

export default function SectorsPage() {
  const { text } = useI18n();
  const [sectors, setSectors] = useState(SECTORS);
  const [source, setSource] = useState<DataSourceState>("loading");
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
        setSource(snapshot.degraded ? "partial" : "api");
      })
      .catch(() => {
        if (!mounted) return;
        setSectors(SECTORS);
        setSource("mock");
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
        <SectorHeatmap sectors={sectors} />
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {sectors.map((s) => (
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
              <div className="text-caption text-text-muted mb-2">{text("核心因子（4 维 conviction）")}</div>
              <div className="grid grid-cols-4 gap-2">
                {FACTORS.map((label, index) => {
                  const value = factorValue(s.id, index);
                  return (
                    <div key={label} className="rounded-xs border border-border-subtle bg-bg-base p-2">
                      <div className="text-caption text-text-muted mb-1">{text(label)}</div>
                      <div className="h-1 bg-bg-surface-raised rounded-full overflow-hidden">
                        <div className="h-full bg-brand-emerald" style={{ width: `${value * 100}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
