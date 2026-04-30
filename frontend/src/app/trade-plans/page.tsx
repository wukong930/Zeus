"use client";

import { TRADE_PLANS } from "@/data/mock";
import { TradePlanCard } from "@/components/TradePlanCard";

export default function TradePlansPage() {
  return (
    <div className="px-8 py-6 max-w-4xl space-y-5 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Trade Plans</h1>
        <p className="text-sm text-text-secondary mt-1">
          每条建议是一份完整的飞行计划——入场、止损、目标、保证金、组合风险一目了然。
        </p>
      </div>

      <div className="space-y-5">
        {TRADE_PLANS.map((plan) => (
          <TradePlanCard key={plan.id} plan={plan} />
        ))}
      </div>
    </div>
  );
}
