"use client";

import { TRADE_PLANS } from "@/data/mock";
import { TradePlanCard } from "@/components/TradePlanCard";
import { MetricTile } from "@/components/MetricTile";
import { Activity, Gauge, Target, WalletCards } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function TradePlansPage() {
  const { text } = useI18n();
  const avgConfidence =
    TRADE_PLANS.reduce((sum, plan) => sum + plan.confidence, 0) / Math.max(TRADE_PLANS.length, 1);
  const avgRiskReward =
    TRADE_PLANS.reduce((sum, plan) => sum + plan.riskReward, 0) / Math.max(TRADE_PLANS.length, 1);
  const avgMargin =
    TRADE_PLANS.reduce((sum, plan) => sum + plan.marginUsage, 0) / Math.max(TRADE_PLANS.length, 1);

  return (
    <div className="px-8 py-6 max-w-5xl space-y-5 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Trade Plans</h1>
        <p className="text-sm text-text-secondary mt-1">
          {text("每条建议是一份完整的飞行计划——入场、止损、目标、保证金、组合风险一目了然。")}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
        <MetricTile label={text("计划数")} value={String(TRADE_PLANS.length)} caption="actionable" icon={Activity} tone="cyan" />
        <MetricTile label={text("平均置信度")} value={`${Math.round(avgConfidence * 100)}%`} caption="model score" icon={Gauge} tone="up" />
        <MetricTile label="平均 R:R" value={`1:${avgRiskReward.toFixed(2)}`} caption="reward/risk" icon={Target} tone="warning" />
        <MetricTile label={text("平均保证金")} value={`${avgMargin.toFixed(1)}%`} caption="margin usage" icon={WalletCards} tone={avgMargin > 25 ? "warning" : "violet"} />
      </div>

      <div className="space-y-5">
        {TRADE_PLANS.map((plan) => (
          <TradePlanCard key={plan.id} plan={plan} />
        ))}
      </div>
    </div>
  );
}
