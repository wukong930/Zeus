"use client";

import { useEffect, useMemo, useState } from "react";

import { type TradePlan } from "@/lib/domain";
import { Card } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { TradePlanCard } from "@/components/TradePlanCard";
import { MetricTile } from "@/components/MetricTile";
import { adoptTradePlan, fetchTradePlansFromApi, reviewTradePlan } from "@/lib/api";
import { Activity, Gauge, Target, WalletCards } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function TradePlansPage() {
  const { text } = useI18n();
  const [plans, setPlans] = useState<TradePlan[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [actingPlanId, setActingPlanId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionErrorTitle, setActionErrorTitle] = useState<string>("交易计划复核失败");
  const avgConfidence = useMemo(
    () => plans.reduce((sum, plan) => sum + plan.confidence, 0) / Math.max(plans.length, 1),
    [plans]
  );
  const avgRiskReward = useMemo(
    () => plans.reduce((sum, plan) => sum + plan.riskReward, 0) / Math.max(plans.length, 1),
    [plans]
  );
  const avgMargin = useMemo(
    () => plans.reduce((sum, plan) => sum + plan.marginUsage, 0) / Math.max(plans.length, 1),
    [plans]
  );
  const executableCount = useMemo(() => plans.filter((plan) => !plan.reviewRequired).length, [plans]);
  const reviewCount = plans.length - executableCount;

  useEffect(() => {
    let mounted = true;
    fetchTradePlansFromApi()
      .then((runtimePlans) => {
        if (!mounted) return;
        setPlans(runtimePlans);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setPlans([]);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleReview = async (plan: TradePlan, decision: "approve" | "reject") => {
    setActingPlanId(plan.id);
    setActionError(null);
    try {
      const updated = await reviewTradePlan(
        plan.id,
        decision,
        decision === "reject" ? "Rejected from Trade Plans review." : "Approved from Trade Plans review."
      );
      setPlans((current) => {
        if (decision === "reject" || updated === null || !isVisibleTradePlan(updated)) {
          return current.filter((item) => item.id !== plan.id);
        }
        return current.map((item) => (item.id === plan.id ? updated : item));
      });
    } catch (error) {
      setActionErrorTitle("交易计划复核失败");
      setActionError(error instanceof Error ? error.message : "交易计划复核失败");
    } finally {
      setActingPlanId(null);
    }
  };

  const handleAdopt = async (plan: TradePlan) => {
    setActingPlanId(plan.id);
    setActionError(null);
    try {
      await adoptTradePlan(plan);
      setPlans((current) => current.filter((item) => item.id !== plan.id));
    } catch (error) {
      setActionErrorTitle("交易计划采纳失败");
      setActionError(error instanceof Error ? error.message : "交易计划采纳失败");
    } finally {
      setActingPlanId(null);
    }
  };

  return (
    <div className="px-8 py-6 max-w-5xl space-y-5 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("Trade Plans")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {text("每条建议是一份完整的飞行计划——入场、止损、目标、保证金、组合风险一目了然。")}
          </p>
        </div>
        <DataSourceBadge state={source} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
        <MetricTile label={text("计划数")} value={String(plans.length)} caption={`${executableCount} ${text("可执行")} / ${reviewCount} ${text("待确认")}`} icon={Activity} tone="cyan" />
        <MetricTile label={text("平均置信度")} value={`${Math.round(avgConfidence * 100)}%`} caption="model score" icon={Gauge} tone="up" />
        <MetricTile label="平均 R:R" value={`1:${avgRiskReward.toFixed(2)}`} caption="reward/risk" icon={Target} tone="warning" />
        <MetricTile label={text("平均保证金")} value={`${avgMargin.toFixed(1)}%`} caption="margin usage" icon={WalletCards} tone={avgMargin > 25 ? "warning" : "violet"} />
      </div>

      <div className="space-y-5">
        {actionError !== null && (
          <Card variant="data" className="border-data-down/40 px-4 py-3 text-sm text-data-down">
            {text(actionErrorTitle)} · {actionError}
          </Card>
        )}
        {plans.length === 0 && source !== "loading" && (
          <Card variant="data" className="py-10 text-center">
            <div className="text-sm text-text-secondary">{text(emptyTradePlanMessage(source))}</div>
          </Card>
        )}
        {plans.map((plan) => (
          <TradePlanCard
            key={plan.id}
            plan={plan}
            actionPending={actingPlanId === plan.id}
            onApproveReview={(item) => handleReview(item, "approve")}
            onRejectReview={(item) => handleReview(item, "reject")}
            onAdoptPlan={handleAdopt}
          />
        ))}
      </div>
    </div>
  );
}

function isVisibleTradePlan(plan: TradePlan): boolean {
  return plan.status === "pending" || plan.status === "pending_review";
}

function emptyTradePlanMessage(source: DataSourceState): string {
  if (source === "fallback") return "交易建议接口暂不可用";
  return "当前暂无待执行或待确认交易计划";
}
