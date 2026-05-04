import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ChartFrameProps {
  title: string;
  subtitle?: string;
  metric?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function ChartFrame({
  title,
  subtitle,
  metric,
  action,
  children,
  className,
  bodyClassName,
}: ChartFrameProps) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-sm border border-border-default bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(3,5,4,0.98))] shadow-data-panel",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-h3 text-text-primary">{title}</h3>
            {metric && (
              <span className="rounded-xs border border-brand-emerald/30 bg-brand-emerald/10 px-2 py-0.5 font-mono text-caption text-brand-emerald-bright">
                {metric}
              </span>
            )}
          </div>
          {subtitle && <p className="mt-1 text-xs text-text-muted">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className={cn("zeus-grid-surface p-4", bodyClassName)}>{children}</div>
    </section>
  );
}
