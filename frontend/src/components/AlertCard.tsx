"use client";

import { Clock, ChevronRight, Sparkles } from "lucide-react";
import { type Alert } from "@/data/mock";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { ConfidenceHalo } from "./ConfidenceHalo";
import { timeAgo } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface AlertCardProps {
  alert: Alert;
  onClick?: () => void;
  glow?: boolean;
}

const severityBorder = {
  critical: "border-l-data-down",
  high: "border-l-severity-high-fg",
  medium: "border-l-brand-orange",
  low: "border-l-data-up",
};

export function AlertCard({ alert, onClick, glow }: AlertCardProps) {
  return (
    <Card
      variant={glow ? "glow" : "flat"}
      glowColor={alert.severity === "critical" ? "red" : "orange"}
      className={cn(
        "border-l-[4px] cursor-pointer transition-all hover:bg-bg-surface-raised",
        severityBorder[alert.severity]
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={alert.severity}>{alert.severity.toUpperCase()}</Badge>
            <span className="text-xs text-text-muted font-mono">{alert.symbol}</span>
            <span className="text-xs text-text-muted">·</span>
            <span className="text-xs text-text-muted">{alert.evaluator}</span>
            <div className="flex-1" />
            <span className="text-caption text-text-muted flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {timeAgo(alert.triggeredAt)}
            </span>
          </div>
          <h3 className="text-h3 text-text-primary mb-1">{alert.title}</h3>
          <p className="text-sm text-text-secondary mb-3 leading-relaxed">{alert.narrative}</p>

          <div className="flex items-center gap-3 text-caption">
            {alert.adversarialPassed && (
              <span className="text-brand-emerald-bright flex items-center gap-1">
                ✓ Adversarial 3/3
              </span>
            )}
            {alert.counterEvidence.length > 0 && (
              <span className="text-data-down flex items-center gap-1">
                ✕ {alert.counterEvidence.length} 反证
              </span>
            )}
            <span className="text-text-muted">samples · {alert.sampleSize}</span>
          </div>
        </div>

        <div className="flex flex-col items-center gap-2 shrink-0">
          <ConfidenceHalo confidence={alert.confidence} sampleSize={alert.sampleSize} />
          <button className="text-caption text-text-muted hover:text-brand-emerald-bright flex items-center gap-1 transition-colors">
            <Sparkles className="w-3 h-3" />
            ⏪ Time Machine
          </button>
        </div>

        <ChevronRight className="w-4 h-4 text-text-muted self-center" />
      </div>
    </Card>
  );
}
