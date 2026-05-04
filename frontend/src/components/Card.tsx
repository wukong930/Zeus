import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "flat" | "elevated" | "active" | "glow" | "data";
  glowColor?: "emerald" | "orange" | "red";
  interactive?: boolean;
}

export function Card({
  className,
  variant = "flat",
  glowColor,
  interactive,
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-sm border p-4 transition duration-200 ease-standard",
        "shadow-inner-panel",
        variant === "flat" &&
          "border-border-subtle bg-[linear-gradient(180deg,rgba(20,20,20,0.82),rgba(10,10,10,0.96))]",
        variant === "elevated" &&
          "border-border-default bg-[linear-gradient(180deg,rgba(31,31,31,0.94),rgba(14,14,14,0.98))] shadow-data-panel",
        variant === "active" &&
          "border-border-default border-l-[3px] border-l-brand-emerald bg-[linear-gradient(180deg,rgba(16,185,129,0.08),rgba(10,10,10,0.96))]",
        variant === "data" &&
          "border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(3,5,4,0.98))] shadow-data-panel",
        variant === "glow" && glowColor === "emerald" && "border-brand-emerald/30 bg-bg-surface shadow-glow-emerald",
        variant === "glow" && glowColor === "orange" && "border-brand-orange/30 bg-bg-surface shadow-glow-orange",
        variant === "glow" && glowColor === "red" && "border-data-down/30 bg-bg-surface shadow-glow-red",
        interactive &&
          "cursor-pointer hover:-translate-y-px hover:border-border-strong hover:bg-bg-surface-raised focus-within:shadow-focus-ring",
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
      className={cn(
        "mb-3 flex items-center justify-between gap-3 border-b border-border-subtle pb-3",
        className
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-h3 text-text-primary tracking-normal", className)} {...props} />;
}

export function CardSubtitle({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-text-muted", className)} {...props} />;
}
