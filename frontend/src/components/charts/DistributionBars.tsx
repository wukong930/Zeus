"use client";

import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

interface DistributionBarsProps {
  buckets: number[];
  tone?: "up" | "down" | "warning";
  height?: number;
  markerIndex?: number;
}

const toneClass = {
  up: "from-data-up/20 to-data-up/70 hover:to-data-up",
  down: "from-data-down/18 to-data-down/70 hover:to-data-down",
  warning: "from-data-warning/18 to-data-warning/70 hover:to-data-warning",
};

export function DistributionBars({
  buckets,
  tone = "up",
  height = 128,
  markerIndex,
}: DistributionBarsProps) {
  const { text } = useI18n();
  const max = Math.max(...buckets, 1);

  return (
    <div className="relative">
      <div
        className="flex items-end gap-1.5 border-b border-border-subtle"
        style={{ height }}
      >
        {buckets.map((bucket, index) => {
          const barHeight = Math.max(8, (bucket / max) * (height - 12));
          const active = markerIndex === index;
          return (
            <div key={`${bucket}-${index}`} className="group relative flex flex-1 items-end justify-center">
              {active && <div className="absolute inset-y-0 w-px bg-brand-orange/80" />}
              <div
                className={cn(
                  "w-full rounded-t-xs bg-gradient-to-t transition-all duration-150",
                  toneClass[tone],
                  active && "ring-1 ring-brand-orange"
                )}
                style={{ height: barHeight }}
                title={`${text("bucket")} ${index + 1}: ${bucket}`}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between font-mono text-caption text-text-muted">
        <span>{text("low")}</span>
        <span>{text("distribution")}</span>
        <span>{text("high")}</span>
      </div>
    </div>
  );
}
