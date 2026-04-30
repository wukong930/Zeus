import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-10 px-5 text-center",
        className
      )}
    >
      {icon && <div className="text-text-muted mb-4 opacity-60">{icon}</div>}
      <h3 className="text-h3 text-text-primary mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-text-muted mb-5 max-w-md">{description}</p>
      )}
      {action}
    </div>
  );
}
