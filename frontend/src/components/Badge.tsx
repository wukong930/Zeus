import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Variant =
  | "neutral"
  | "emerald"
  | "orange"
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
  neutral: "bg-bg-surface-raised text-text-secondary",
  emerald: "bg-brand-emerald/15 text-brand-emerald-bright",
  orange: "bg-brand-orange/15 text-brand-orange",
  up: "bg-data-up/15 text-data-up",
  down: "bg-data-down/15 text-data-down",
  critical: "bg-[rgba(239,68,68,0.12)] text-severity-critical-fg",
  high: "bg-[rgba(245,158,11,0.12)] text-severity-high-fg",
  medium: "bg-[rgba(234,179,8,0.10)] text-severity-medium-fg",
  low: "bg-[rgba(34,197,94,0.10)] text-severity-low-fg",
};

export function Badge({ variant = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-xs px-2 h-5 text-xs font-medium whitespace-nowrap",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
