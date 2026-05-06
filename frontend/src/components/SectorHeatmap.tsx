"use client";

import type { SectorData } from "@/data/mock";
import { cn } from "@/lib/utils";
import { formatPercent } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export function SectorHeatmap({
  sectors,
  emptyMessage = "暂无板块快照",
}: {
  sectors: SectorData[];
  emptyMessage?: string;
}) {
  const { text } = useI18n();

  if (sectors.length === 0) {
    return (
      <div className="flex min-h-[220px] items-center justify-center rounded-sm border border-dashed border-border-subtle bg-bg-base/50 px-4 text-center text-sm text-text-secondary">
        {text(emptyMessage)}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {sectors.map((sector) => (
        <div key={sector.id} className="grid grid-cols-[64px_minmax(0,1fr)_82px] items-center gap-3">
          <div className="min-w-0">
            <div className="truncate text-xs font-medium text-text-secondary">{text(sector.name)}</div>
            <div className="mt-1 h-px bg-border-subtle" />
          </div>
          <div className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
            {sector.symbols.map((sym) => {
              const isUp = sym.change >= 0;
              const intensity = Math.min(1, Math.abs(sym.change) / 2.5);
              const borderColor = isUp
                ? `rgba(16, 185, 129, ${intensity * 0.42 + 0.22})`
                : `rgba(239, 68, 68, ${intensity * 0.42 + 0.22})`;
              const background = isUp
                ? `linear-gradient(180deg, rgba(16,185,129,${intensity * 0.28 + 0.12}), rgba(5,7,6,0.96))`
                : `linear-gradient(180deg, rgba(239,68,68,${intensity * 0.26 + 0.1}), rgba(5,7,6,0.96))`;
              return (
                <div
                  key={sym.code}
                  className={cn(
                    "relative min-h-[66px] cursor-pointer rounded-sm border px-2 py-2 shadow-inner-panel transition duration-150 hover:-translate-y-px hover:border-border-strong",
                    sym.signalActive && "shadow-glow-orange"
                  )}
                  style={{ background, borderColor }}
                  title={`${sym.code} · ${text(sym.name)} · ${formatPercent(sym.change)}`}
                >
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/10" />
                  {sym.signalActive && (
                    <div className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-brand-orange shadow-glow-orange animate-heartbeat" />
                  )}
                  <div className="pr-3 text-xs font-semibold text-text-primary">{sym.code}</div>
                  <div className="mt-0.5 truncate text-[10px] leading-tight text-text-muted">{text(sym.name)}</div>
                  <div className={cn("mt-1 font-mono text-sm leading-none tabular-nums", isUp ? "text-data-up" : "text-data-down")}>
                    {formatPercent(sym.change)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="shrink-0 text-right">
            <div className="text-caption text-text-muted">conviction</div>
            <div className={cn("font-mono text-sm tabular-nums", sector.conviction >= 0 ? "text-data-up" : "text-data-down")}>
              {sector.conviction >= 0 ? "+" : ""}
              {sector.conviction.toFixed(2)}
            </div>
            <div className="mt-1 h-1 rounded-full bg-bg-surface-raised">
              <div
                className={cn("h-full rounded-full", sector.conviction >= 0 ? "bg-data-up" : "bg-data-down")}
                style={{ width: `${Math.min(100, Math.abs(sector.conviction) * 100)}%` }}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
