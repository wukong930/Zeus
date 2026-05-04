"use client";

import { useEffect, useState } from "react";
import { Activity, Gauge, GitBranch, ShieldCheck, Waves } from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { MetricTile } from "@/components/MetricTile";
import { fetchBacktestQualitySummary, type BacktestQualitySummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export default function StrategyForgePage() {
  const { text } = useI18n();
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
        <h1 className="text-h1 text-text-primary">{text("Strategy Forge")}</h1>
        <p className="text-sm text-text-secondary mt-1">{text("策略研究、回测、参数调优 · vectorbt + DoWhy")}</p>
      </div>

      <div className="grid grid-cols-12 gap-5">
        <MetricTile
          className="col-span-12 md:col-span-6 xl:col-span-3"
          label="Calibration"
          value={summary?.guardrails.calibration_strategy.toUpperCase() ?? "-"}
          caption={summary?.guardrails.decision_grade_required ? "decision-grade" : "diagnostic"}
          icon={ShieldCheck}
          tone="up"
        />
        <MetricTile
          className="col-span-12 md:col-span-6 xl:col-span-3"
          label="Multiple Testing"
          value={summary ? "DSR + FDR" : "-"}
          caption="raw Sharpe gated"
          icon={Gauge}
          tone="cyan"
        />
        <MetricTile
          className="col-span-12 md:col-span-6 xl:col-span-3"
          label="Path Risk"
          value={summary ? pct(summary.path_metrics.max_drawdown) : "-"}
          caption="max drawdown"
          icon={Waves}
          tone={summary && summary.path_metrics.max_drawdown <= -0.1 ? "down" : "warning"}
        />
        <MetricTile
          className="col-span-12 md:col-span-6 xl:col-span-3"
          label="PIT Universe"
          value={summary?.universe.valid ? text("VALID") : summary ? text("BLOCKED") : "-"}
          caption={summary ? `${summary.universe.active_symbols.length} ${text("active symbols")}` : text("loading")}
          icon={GitBranch}
          tone={summary?.universe.valid ?? true ? "up" : "down"}
        />
      </div>

      {error && (
        <Card variant="data">
          <div className="text-sm text-data-down">{error}</div>
        </Card>
      )}

      <div className="grid grid-cols-12 gap-5">
        <Card variant="data" className="col-span-12 xl:col-span-7">
          <CardHeader>
            <div>
              <CardTitle>Regime Profile</CardTitle>
              <CardSubtitle>Sharpe / hit rate / drawdown by market state</CardSubtitle>
            </div>
            <Badge variant="emerald">{summary?.walk_forward.mode ?? "rolling"}</Badge>
          </CardHeader>
          <div className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-base shadow-inner-panel">
            <table className="w-full text-sm">
              <thead className="text-caption text-text-muted">
                <tr className="border-b border-border-subtle bg-bg-panel">
                  <th className="text-left px-3 py-2 font-medium">{text("Regime")}</th>
                  <th className="text-right px-3 py-2 font-medium">N</th>
                  <th className="text-right px-3 py-2 font-medium">{text("Win")}</th>
                  <th className="text-right px-3 py-2 font-medium">Sharpe</th>
                  <th className="text-right px-3 py-2 font-medium">MDD</th>
                </tr>
              </thead>
              <tbody>
                {(summary?.regime_profile ?? []).map((row) => (
                  <tr key={row.regime} className="border-b border-border-subtle last:border-b-0 hover:bg-bg-surface-raised/50">
                    <td className="px-3 py-2 text-text-primary font-mono">{row.regime}</td>
                    <td className="px-3 py-2 text-right text-text-secondary">{row.sample_size}</td>
                    <td className="px-3 py-2 text-right text-data-up">{pct(row.win_rate)}</td>
                    <td className="px-3 py-2 text-right text-text-primary">{num(row.sharpe)}</td>
                    <td className="px-3 py-2 text-right text-data-down">{pct(row.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card variant="data" className="col-span-12 xl:col-span-5">
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
          <div className="mt-4 rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-caption text-text-muted shadow-inner-panel">
            {text("Walk-forward")} {summary?.walk_forward.training_years ?? 3}y / {summary?.walk_forward.test_months ?? 3}m / {summary?.walk_forward.step_months ?? 1}m
          </div>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value, up = false }: { label: string; value: string; up?: boolean }) {
  const { text } = useI18n();

  return (
    <div className="min-h-20 rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
      <div className="text-caption text-text-muted">{text(label)}</div>
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
