import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Variant =
  | "neutral"
  | "emerald"
  | "orange"
  | "blue"
  | "cyan"
  | "violet"
  | "up"
  | "down"
  | "critical"
  | "high"
  | "medium"
  | "low";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variantStyles: Record<Variant, string> = {
  neutral: "border-border-subtle bg-bg-surface-raised text-text-secondary",
  emerald: "border-brand-emerald/30 bg-brand-emerald/15 text-brand-emerald-bright",
  orange: "border-brand-orange/30 bg-brand-orange/15 text-brand-orange",
  blue: "border-brand-blue/30 bg-brand-blue/15 text-brand-blue",
  cyan: "border-brand-cyan/30 bg-brand-cyan/15 text-brand-cyan",
  violet: "border-brand-violet/30 bg-brand-violet/15 text-brand-violet",
  up: "border-data-up/30 bg-data-up/15 text-data-up",
  down: "border-data-down/30 bg-data-down/15 text-data-down",
  critical: "border-data-down/35 bg-[rgba(239,68,68,0.12)] text-severity-critical-fg",
  high: "border-data-warning/35 bg-[rgba(245,158,11,0.12)] text-severity-high-fg",
  medium: "border-severity-medium-fg/30 bg-[rgba(234,179,8,0.10)] text-severity-medium-fg",
  low: "border-data-up/30 bg-[rgba(34,197,94,0.10)] text-severity-low-fg",
};

export function Badge({ variant = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-xs border px-2 text-xs font-medium shadow-inner-panel",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
