import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "flat" | "elevated" | "active" | "glow";
  glowColor?: "emerald" | "orange" | "red";
}

export function Card({ className, variant = "flat", glowColor, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-sm border border-border-subtle p-4 transition-colors duration-200 ease-standard",
        variant === "flat" && "bg-bg-surface",
        variant === "elevated" && "bg-bg-surface-raised shadow-sm",
        variant === "active" && "bg-bg-surface border-l-[3px] border-l-brand-emerald",
        variant === "glow" && glowColor === "emerald" && "bg-bg-surface shadow-glow-emerald",
        variant === "glow" && glowColor === "orange" && "bg-bg-surface shadow-glow-orange",
        variant === "glow" && glowColor === "red" && "bg-bg-surface shadow-glow-red",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex items-center justify-between border-b border-border-subtle pb-3 mb-3", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-h3 text-text-primary", className)} {...props} />;
}

export function CardSubtitle({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-text-muted", className)} {...props} />;
}
