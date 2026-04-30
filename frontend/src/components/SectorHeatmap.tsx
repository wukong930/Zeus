"use client";

import { SECTORS } from "@/data/mock";
import { cn } from "@/lib/utils";
import { formatPercent } from "@/lib/utils";

export function SectorHeatmap() {
  return (
    <div className="space-y-2">
      {SECTORS.map((sector) => (
        <div key={sector.id} className="flex items-center gap-3">
          <div className="w-16 text-xs text-text-muted shrink-0">{sector.name}</div>
          <div className="flex-1 grid grid-cols-5 gap-1">
            {sector.symbols.map((sym) => {
              const isUp = sym.change >= 0;
              const intensity = Math.min(1, Math.abs(sym.change) / 2.5);
              const color = isUp
                ? `rgba(16, 185, 129, ${intensity * 0.5 + 0.15})`
                : `rgba(239, 68, 68, ${intensity * 0.5 + 0.15})`;
              return (
                <div
                  key={sym.code}
                  className={cn(
                    "relative h-12 rounded-sm border border-border-subtle px-2 py-1 transition-transform hover:scale-105 cursor-pointer overflow-hidden",
                    sym.signalActive && "shadow-glow-orange"
                  )}
                  style={{ background: color }}
                  title={`${sym.code} · ${sym.name} · ${formatPercent(sym.change)}`}
                >
                  {sym.signalActive && (
                    <div className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-brand-orange animate-heartbeat" />
                  )}
                  <div className="text-xs font-semibold text-text-primary">{sym.code}</div>
                  <div className={cn("text-caption font-mono tabular-nums", isUp ? "text-data-up" : "text-data-down")}>
                    {formatPercent(sym.change)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="w-20 text-right shrink-0">
            <div className="text-caption text-text-muted">conviction</div>
            <div className={cn("font-mono text-sm tabular-nums", sector.conviction >= 0 ? "text-data-up" : "text-data-down")}>
              {sector.conviction >= 0 ? "+" : ""}
              {sector.conviction.toFixed(2)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
