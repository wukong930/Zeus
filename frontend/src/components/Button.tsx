import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "action" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantStyles: Record<Variant, string> = {
  primary:
    "bg-brand-emerald text-white hover:bg-brand-emerald-hover active:scale-[0.98]",
  action:
    "bg-brand-orange text-white hover:bg-brand-orange-hover active:scale-[0.98] shadow-glow-orange",
  secondary:
    "bg-transparent border border-border-default text-text-primary hover:bg-bg-surface-raised",
  ghost:
    "bg-transparent text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary",
  destructive:
    "bg-data-down text-white hover:bg-red-700 active:scale-[0.98]",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-7 px-3 text-xs",
  md: "h-9 px-4 text-body",
  lg: "h-11 px-6 text-h3",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-sm font-medium transition-all duration-100 ease-standard disabled:opacity-30 disabled:cursor-not-allowed disabled:active:scale-100",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";
