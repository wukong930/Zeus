"use client";

import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "action" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantStyles: Record<Variant, string> = {
  primary:
    "border border-brand-emerald/40 bg-brand-emerald text-white shadow-glow-emerald hover:bg-brand-emerald-hover active:scale-[0.98]",
  action:
    "border border-brand-orange/40 bg-brand-orange text-white shadow-glow-orange hover:bg-brand-orange-hover active:scale-[0.98]",
  secondary:
    "border border-border-default bg-bg-surface text-text-primary hover:border-border-strong hover:bg-bg-surface-raised",
  ghost:
    "border border-transparent bg-transparent text-text-secondary hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary",
  destructive:
    "border border-data-down/40 bg-data-down text-white shadow-glow-red hover:bg-red-700 active:scale-[0.98]",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-7 px-3 text-xs",
  md: "h-9 px-4 text-body",
  lg: "h-11 px-6 text-h3",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", children, ...props }, ref) => {
    const { text } = useI18n();

    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-sm font-medium transition-all duration-100 ease-standard disabled:opacity-30 disabled:cursor-not-allowed disabled:active:scale-100",
          "focus-visible:shadow-focus-ring focus-visible:outline-none",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {typeof children === "string" ? text(children) : children}
      </button>
    );
  }
);
Button.displayName = "Button";
