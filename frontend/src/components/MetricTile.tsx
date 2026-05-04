import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type MetricTone = "neutral" | "up" | "down" | "warning" | "cyan" | "violet";

const toneStyles: Record<MetricTone, string> = {
  neutral: "border-border-subtle text-text-secondary",
  up: "border-data-up/30 text-data-up",
  down: "border-data-down/30 text-data-down",
  warning: "border-data-warning/30 text-data-warning",
  cyan: "border-brand-cyan/30 text-brand-cyan",
  violet: "border-brand-violet/30 text-brand-violet",
};

interface MetricTileProps {
  label: string;
  value: string;
  trend?: string;
  caption?: string;
  icon?: LucideIcon;
  tone?: MetricTone;
  className?: string;
}

export function MetricTile({
  label,
  value,
  trend,
  caption,
  icon: Icon,
  tone = "neutral",
  className,
}: MetricTileProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-sm border bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(5,7,6,0.98))] p-3 shadow-data-panel",
        toneStyles[tone],
        className
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/5" />
      <div className="flex items-center justify-between gap-3">
        <div className="text-caption uppercase tracking-wide text-text-muted">{label}</div>
        {Icon && (
          <div className={cn("flex h-7 w-7 items-center justify-center rounded-xs border bg-bg-base", toneStyles[tone])}>
            <Icon className="h-3.5 w-3.5" />
          </div>
        )}
      </div>
      <div className="mt-3 font-mono text-2xl leading-none text-text-primary tabular-nums">
        {value}
      </div>
      {(trend || caption) && (
        <div className="mt-2 flex items-center gap-2 text-caption">
          {trend && <span className={cn("font-mono tabular-nums", toneStyles[tone])}>{trend}</span>}
          {caption && <span className="truncate text-text-muted">{caption}</span>}
        </div>
      )}
    </div>
  );
}
