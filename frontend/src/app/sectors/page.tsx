"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import { Badge } from "@/components/Badge";
import { SECTORS } from "@/data/mock";
import { cn } from "@/lib/utils";

export default function SectorsPage() {
  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Sectors</h1>
        <p className="text-sm text-text-secondary mt-1">
          板块层方向判断 + 各品种活跃度 + conviction 因子
        </p>
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>板块热力图</CardTitle>
            <CardSubtitle>橙色脉动 = 信号活跃 · 颜色亮度 = 涨跌幅</CardSubtitle>
          </div>
        </CardHeader>
        <SectorHeatmap />
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {SECTORS.map((s) => (
          <Card key={s.id} variant="flat">
            <CardHeader>
              <div className="flex items-center gap-3">
                <CardTitle>{s.name}</CardTitle>
                <Badge variant={s.conviction >= 0 ? "up" : "down"}>
                  conviction {s.conviction >= 0 ? "+" : ""}{s.conviction.toFixed(2)}
                </Badge>
              </div>
            </CardHeader>
            <div className="space-y-2">
              {s.symbols.map((sym) => (
                <div key={sym.code} className="flex items-center gap-3">
                  <div className="font-mono text-sm w-12">{sym.code}</div>
                  <div className="text-text-secondary text-sm flex-1">{sym.name}</div>
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
              <div className="text-caption text-text-muted mb-2">核心因子（4 维 conviction）</div>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "成本", value: 0.4 + Math.random() * 0.4 },
                  { label: "库存", value: 0.3 + Math.random() * 0.5 },
                  { label: "季节", value: 0.5 + Math.random() * 0.3 },
                  { label: "利润", value: 0.4 + Math.random() * 0.4 },
                ].map((f) => (
                  <div key={f.label} className="bg-bg-base rounded-xs p-2">
                    <div className="text-caption text-text-muted mb-1">{f.label}</div>
                    <div className="h-1 bg-bg-surface-raised rounded-full overflow-hidden">
                      <div className="h-full bg-brand-emerald" style={{ width: `${f.value * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
