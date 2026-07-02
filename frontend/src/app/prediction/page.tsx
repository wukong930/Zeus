"use client";

import { useEffect, useState } from "react";
import { Activity, Award, Gauge, ShieldCheck, TrendingUp } from "lucide-react";

import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { MetricTile } from "@/components/MetricTile";
import {
  fetchForecastHistory,
  fetchForecastOverview,
  type ForecastOverview,
  type ForecastRecordView,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function shortDate(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "—";
}

export default function PredictionPage() {
  const { text } = useI18n();
  const [overview, setOverview] = useState<ForecastOverview | null>(null);
  const [history, setHistory] = useState<ForecastRecordView[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");

  useEffect(() => {
    let mounted = true;
    Promise.all([fetchForecastOverview(), fetchForecastHistory(30)])
      .then(([ov, hist]) => {
        if (!mounted) return;
        setOverview(ov);
        setHistory(hist);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setOverview(null);
        setHistory([]);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const perf = overview?.shadowPerformance ?? null;
  const latest = overview?.latest ?? null;
  const live = overview?.live ?? null;
  const authoritative = overview?.promoted ?? false;
  const deflated = perf?.deflated ?? null;

  return (
    <div className="px-8 py-6 max-w-5xl space-y-5 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("预测信号")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {text(
              "横截面反转因子的受治理生命周期：影子跟踪 → 治理审批 → 权威（有界）→ 实盘背离自动降级。此视图只读，晋升在治理队列完成。"
            )}
          </p>
        </div>
        <DataSourceBadge state={source} />
      </div>

      {overview && (
        <Card variant="data" className="flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4">
          <IdentityField label={text("信号")} value={overview.signal} />
          <IdentityField label={text("模型版本")} value={overview.modelVersion} />
          {latest && <IdentityField label="as_of" value={shortDate(latest.asOf)} />}
          {latest && <IdentityField label={text("持有期")} value={`${latest.horizonDays}d`} />}
          <div className="ml-auto">
            <Badge variant={authoritative ? "emerald" : "cyan"} className="gap-1.5">
              <ShieldCheck className="h-3 w-3" />
              {text(authoritative ? "权威（有界）" : "影子（非权威）")}
            </Badge>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
        <MetricTile
          label={text("已结算预测")}
          value={perf ? String(perf.resolved) : "—"}
          caption="resolved shadow"
          icon={Activity}
          tone="cyan"
        />
        <MetricTile label={text("胜率")} value={pct(perf?.winRate)} caption="win rate" icon={Gauge} tone="up" />
        <MetricTile
          label={text("单期净收益")}
          value={pct(perf?.meanReturn, 2)}
          caption="mean / period"
          icon={TrendingUp}
          tone={(perf?.meanReturn ?? 0) >= 0 ? "up" : "down"}
        />
        <MetricTile
          label="Deflated Sharpe"
          value={deflated ? deflated.deflated_sharpe.toFixed(2) : perf?.sharpe != null ? perf.sharpe.toFixed(2) : "—"}
          caption={deflated ? `p=${deflated.deflated_pvalue.toFixed(3)}` : "sharpe"}
          icon={Award}
          tone={deflated?.passed_gate ? "up" : "violet"}
        />
      </div>

      {latest ? (
        <Card variant="data" className="space-y-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-h3 text-text-primary">{text("当前目标持仓")}</h2>
            <span className="text-caption text-text-muted">
              {latest.universeSize} {text("品种")} · {text(latest.decisionGrade ? "决策级" : "咨询/影子")}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <LegList title={text("做多（输家）")} symbols={latest.long} tone="up" />
            <LegList title={text("做空（赢家）")} symbols={latest.short} tone="down" />
          </div>
        </Card>
      ) : (
        source !== "loading" && (
          <Card variant="data" className="py-10 text-center text-sm text-text-secondary">
            {text(source === "fallback" ? "预测接口暂不可用" : "暂无预测记录")}
          </Card>
        )
      )}

      {live && live.periods > 0 && (
        <Card
          variant={live.breached ? "glow" : "data"}
          glowColor={live.breached ? "red" : undefined}
          className="space-y-2 p-5"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-h3 text-text-primary">{text("实盘背离监控")}</h2>
            <Badge variant={live.breached ? "orange" : "emerald"}>
              {text(live.breached ? "触发降级" : "健康")}
            </Badge>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <IdentityField label={text("实盘期数")} value={String(live.periods)} />
            <IdentityField label="live sharpe" value={live.sharpe.toFixed(2)} />
            <IdentityField label={text("最大回撤")} value={pct(live.maxDrawdown)} />
          </div>
          {live.reason && <p className="text-xs text-data-down">{live.reason}</p>}
        </Card>
      )}

      {history.length > 0 && (
        <Card variant="data" className="overflow-hidden p-0">
          <div className="border-b border-border-subtle px-4 py-3 text-h3 text-text-primary">
            {text("近期预测")}
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-caption uppercase text-text-muted">
                <th className="px-4 py-2 text-left font-normal">as_of</th>
                <th className="px-4 py-2 text-left font-normal">{text("等级")}</th>
                <th className="px-4 py-2 text-right font-normal">{text("已实现收益")}</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row) => (
                <tr key={row.id} className="border-t border-border-subtle/60">
                  <td className="px-4 py-2 font-mono text-text-secondary">{shortDate(row.asOf)}</td>
                  <td className="px-4 py-2">
                    <Badge variant={row.decisionGrade ? "emerald" : "neutral"}>
                      {text(row.decisionGrade ? "决策级" : "影子")}
                    </Badge>
                  </td>
                  <td
                    className={cn(
                      "px-4 py-2 text-right font-mono tabular-nums",
                      (row.realizedReturn ?? 0) >= 0 ? "text-data-up" : "text-data-down"
                    )}
                  >
                    {row.realizedReturn === null ? text("待结算") : pct(row.realizedReturn, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function IdentityField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-caption uppercase tracking-wide text-text-muted">{label}</div>
      <div className="mt-0.5 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function LegList({ title, symbols, tone }: { title: string; symbols: string[]; tone: "up" | "down" }) {
  const { text } = useI18n();
  const color = tone === "up" ? "text-data-up border-data-up/30" : "text-data-down border-data-down/30";
  return (
    <div>
      <div className="mb-2 text-caption uppercase tracking-wide text-text-muted">{title}</div>
      {symbols.length === 0 ? (
        <div className="text-xs text-text-muted">{text("无")}</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {symbols.map((symbol) => (
            <span key={symbol} className={cn("rounded-xs border px-2 py-1 font-mono text-xs", color)}>
              {symbol}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
