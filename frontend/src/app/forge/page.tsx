"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Activity, Gauge, GitBranch, ShieldCheck, Waves } from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { fetchBacktestQualitySummary, type BacktestQualitySummary } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function StrategyForgePage() {
  const [summary, setSummary] = useState<BacktestQualitySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchBacktestQualitySummary()
      .then((data) => {
        if (mounted) setSummary(data);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : "failed");
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Strategy Forge</h1>
        <p className="text-sm text-text-secondary mt-1">策略研究、回测、参数调优 · vectorbt + DoWhy</p>
      </div>

      <div className="grid grid-cols-12 gap-5">
        <QualityCard
          className="col-span-12 md:col-span-6 xl:col-span-3"
          icon={<ShieldCheck className="w-4 h-4" />}
          label="Calibration"
          value={summary?.guardrails.calibration_strategy.toUpperCase() ?? "-"}
          desc={summary?.guardrails.decision_grade_required ? "decision-grade" : "diagnostic"}
          positive
        />
        <QualityCard
          className="col-span-12 md:col-span-6 xl:col-span-3"
          icon={<Gauge className="w-4 h-4" />}
          label="Multiple Testing"
          value={summary ? "DSR + FDR" : "-"}
          desc="raw Sharpe gated"
          positive
        />
        <QualityCard
          className="col-span-12 md:col-span-6 xl:col-span-3"
          icon={<Waves className="w-4 h-4" />}
          label="Path Risk"
          value={summary ? pct(summary.path_metrics.max_drawdown) : "-"}
          desc="max drawdown"
          positive={summary ? summary.path_metrics.max_drawdown > -0.1 : true}
        />
        <QualityCard
          className="col-span-12 md:col-span-6 xl:col-span-3"
          icon={<GitBranch className="w-4 h-4" />}
          label="PIT Universe"
          value={summary?.universe.valid ? "VALID" : summary ? "BLOCKED" : "-"}
          desc={summary ? `${summary.universe.active_symbols.length} active symbols` : "loading"}
          positive={summary?.universe.valid ?? true}
        />
      </div>

      {error && (
        <Card variant="flat">
          <div className="text-sm text-data-down">{error}</div>
        </Card>
      )}

      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-12 xl:col-span-7">
          <CardHeader>
            <div>
              <CardTitle>Regime Profile</CardTitle>
              <CardSubtitle>Sharpe / hit rate / drawdown by market state</CardSubtitle>
            </div>
            <Badge variant="emerald">{summary?.walk_forward.mode ?? "rolling"}</Badge>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-caption text-text-muted">
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-2 font-medium">Regime</th>
                  <th className="text-right py-2 font-medium">N</th>
                  <th className="text-right py-2 font-medium">Win</th>
                  <th className="text-right py-2 font-medium">Sharpe</th>
                  <th className="text-right py-2 font-medium">MDD</th>
                </tr>
              </thead>
              <tbody>
                {(summary?.regime_profile ?? []).map((row) => (
                  <tr key={row.regime} className="border-b border-border-subtle last:border-b-0">
                    <td className="py-2 text-text-primary font-mono">{row.regime}</td>
                    <td className="py-2 text-right text-text-secondary">{row.sample_size}</td>
                    <td className="py-2 text-right text-data-up">{pct(row.win_rate)}</td>
                    <td className="py-2 text-right text-text-primary">{num(row.sharpe)}</td>
                    <td className="py-2 text-right text-data-down">{pct(row.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card variant="flat" className="col-span-12 xl:col-span-5">
          <CardHeader>
            <div>
              <CardTitle>Path Metrics</CardTitle>
              <CardSubtitle>Underwater / pain / recovery / CVaR</CardSubtitle>
            </div>
            <Activity className="w-4 h-4 text-brand-emerald" />
          </CardHeader>
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Total Return" value={summary ? pct(summary.path_metrics.total_return) : "-"} up />
            <Metric label="CVaR 95" value={summary ? pct(summary.path_metrics.cvar95) : "-"} />
            <Metric label="Pain Ratio" value={summary ? num(summary.path_metrics.pain_ratio) : "-"} up />
            <Metric label="Recovery" value={summary ? num(summary.path_metrics.recovery_factor) : "-"} up />
            <Metric label="P80 MAE" value={summary?.path_metrics.mae_p80 != null ? pct(summary.path_metrics.mae_p80) : "-"} />
            <Metric label="P80 MFE" value={summary?.path_metrics.mfe_p80 != null ? pct(summary.path_metrics.mfe_p80) : "-"} up />
          </div>
          <div className="mt-4 text-caption text-text-muted">
            Walk-forward {summary?.walk_forward.training_years ?? 3}y / {summary?.walk_forward.test_months ?? 3}m / {summary?.walk_forward.step_months ?? 1}m
          </div>
        </Card>
      </div>
    </div>
  );
}

function QualityCard({
  className,
  icon,
  label,
  value,
  desc,
  positive,
}: {
  className?: string;
  icon: ReactNode;
  label: string;
  value: string;
  desc: string;
  positive: boolean;
}) {
  return (
    <Card variant="flat" className={className}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-text-muted">{icon}</div>
        <Badge variant={positive ? "emerald" : "orange"}>{positive ? "guarded" : "review"}</Badge>
      </div>
      <div className="mt-4 text-caption text-text-muted">{label}</div>
      <div className={cn("mt-1 text-h2 font-mono break-words", positive ? "text-text-primary" : "text-data-down")}>
        {value}
      </div>
      <div className="mt-1 text-caption text-text-muted">{desc}</div>
    </Card>
  );
}

function Metric({ label, value, up = false }: { label: string; value: string; up?: boolean }) {
  return (
    <div className="bg-bg-base rounded-sm p-3 min-h-20">
      <div className="text-caption text-text-muted">{label}</div>
      <div className={cn("text-lg font-mono mt-1 break-words", up ? "text-data-up" : "text-data-down")}>
        {value}
      </div>
    </div>
  );
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function num(value: number): string {
  return value.toFixed(2);
}
