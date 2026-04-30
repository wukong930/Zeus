"use client";

import { ArrowDown, ArrowUp, TrendingUp, TrendingDown } from "lucide-react";
import { Card } from "./Card";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { ConfidenceHalo } from "./ConfidenceHalo";
import { type TradePlan } from "@/data/mock";
import { cn, formatNumber, formatPercent } from "@/lib/utils";

interface TradePlanCardProps {
  plan: TradePlan;
}

export function TradePlanCard({ plan }: TradePlanCardProps) {
  const isLong = plan.direction === "long";
  // Normalize prices to 0..1 range for visualization
  const lo = Math.min(plan.entryPrice, plan.stopLoss, plan.takeProfit, plan.currentPrice);
  const hi = Math.max(plan.entryPrice, plan.stopLoss, plan.takeProfit, plan.currentPrice);
  const range = hi - lo;
  const norm = (v: number) => ((v - lo) / range) * 100;

  return (
    <Card variant="elevated" className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-h3 font-mono">{plan.symbol}</span>
            <Badge variant={isLong ? "up" : "down"}>
              {isLong ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
              {isLong ? "做多" : "做空"} {plan.size} 手
            </Badge>
          </div>
          <div className="text-caption text-text-muted">{plan.symbolName}</div>
        </div>
        <ConfidenceHalo confidence={plan.confidence} sampleSize={47} size={48} />
      </div>

      {/* Price plan visualization */}
      <div className="bg-bg-base rounded-sm p-4 space-y-3">
        <div className="relative h-2 bg-bg-surface-raised rounded-full overflow-hidden">
          {/* Risk zone */}
          {isLong ? (
            <div
              className="absolute top-0 left-0 h-full bg-data-down/30"
              style={{ width: `${norm(plan.entryPrice)}%` }}
            />
          ) : (
            <div
              className="absolute top-0 right-0 h-full bg-data-down/30"
              style={{ width: `${100 - norm(plan.entryPrice)}%` }}
            />
          )}
          {/* Reward zone */}
          {isLong ? (
            <div
              className="absolute top-0 h-full bg-data-up/30"
              style={{ left: `${norm(plan.entryPrice)}%`, right: `${100 - norm(plan.takeProfit)}%` }}
            />
          ) : (
            <div
              className="absolute top-0 h-full bg-data-up/30"
              style={{ left: `${norm(plan.takeProfit)}%`, right: `${100 - norm(plan.entryPrice)}%` }}
            />
          )}
          {/* Stop loss marker */}
          <div
            className="absolute top-0 w-0.5 h-full bg-data-down"
            style={{ left: `${norm(plan.stopLoss)}%` }}
          />
          {/* Entry marker */}
          <div
            className="absolute top-0 w-0.5 h-full bg-text-primary"
            style={{ left: `${norm(plan.entryPrice)}%` }}
          />
          {/* Take profit marker */}
          <div
            className="absolute top-0 w-0.5 h-full bg-data-up"
            style={{ left: `${norm(plan.takeProfit)}%` }}
          />
          {/* Current price marker (animated) */}
          <div
            className="absolute -top-1 w-3 h-4 -ml-1.5 flex items-center justify-center"
            style={{ left: `${norm(plan.currentPrice)}%` }}
          >
            <div className="w-2 h-2 rounded-full bg-brand-orange animate-heartbeat shadow-glow-orange" />
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2 text-xs font-mono tabular-nums">
          <div>
            <div className="text-text-muted text-caption">止损</div>
            <div className="text-data-down">{formatNumber(plan.stopLoss, { decimals: 0 })}</div>
          </div>
          <div>
            <div className="text-text-muted text-caption">入场</div>
            <div className="text-text-primary">{formatNumber(plan.entryPrice, { decimals: 0 })}</div>
          </div>
          <div>
            <div className="text-text-muted text-caption">当前</div>
            <div className="text-brand-orange">{formatNumber(plan.currentPrice, { decimals: 0 })}</div>
          </div>
          <div>
            <div className="text-text-muted text-caption">目标</div>
            <div className="text-data-up">{formatNumber(plan.takeProfit, { decimals: 0 })}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Risk" value={formatPercent(plan.riskPercent)} colorClass="text-data-down" icon={<TrendingDown className="w-3 h-3" />} />
        <Stat label="Reward" value={formatPercent(plan.rewardPercent)} colorClass="text-data-up" icon={<TrendingUp className="w-3 h-3" />} />
        <Stat label="R : R" value={`1 : ${plan.riskReward.toFixed(2)}`} colorClass="text-text-primary" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <ProgressBar label="保证金占用" value={plan.marginUsage} max={50} />
        <ProgressBar label="组合风险" value={plan.portfolioRisk} max={20} status={plan.portfolioRisk < 10 ? "healthy" : "warning"} />
      </div>

      <div className="text-xs text-text-secondary leading-relaxed border-t border-border-subtle pt-3">
        <span className="text-text-muted">信号摘要 ·</span> {plan.signalSummary}
      </div>

      <div className="flex gap-2">
        <Button variant="action" size="md" className="flex-1">
          采纳建议
        </Button>
        <Button variant="secondary" size="md">
          修改
        </Button>
        <Button variant="ghost" size="md">
          拒绝
        </Button>
      </div>
    </Card>
  );
}

function Stat({
  label,
  value,
  colorClass,
  icon,
}: {
  label: string;
  value: string;
  colorClass: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="bg-bg-base rounded-sm p-3">
      <div className="text-caption text-text-muted mb-1">{label}</div>
      <div className={cn("font-mono text-sm font-semibold flex items-center gap-1 tabular-nums", colorClass)}>
        {icon}
        {value}
      </div>
    </div>
  );
}

function ProgressBar({
  label,
  value,
  max,
  status = "healthy",
}: {
  label: string;
  value: number;
  max: number;
  status?: "healthy" | "warning";
}) {
  const pct = (value / max) * 100;
  return (
    <div>
      <div className="flex justify-between text-caption mb-1">
        <span className="text-text-muted">{label}</span>
        <span className={cn("font-mono", status === "healthy" ? "text-text-secondary" : "text-severity-high-fg")}>
          {value}%
        </span>
      </div>
      <div className="h-1.5 bg-bg-surface-raised rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full", status === "healthy" ? "bg-brand-emerald" : "bg-severity-high-fg")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
