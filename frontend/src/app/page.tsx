"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { CausalWeb } from "@/components/CausalWeb";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import { AlertCard } from "@/components/AlertCard";
import { Badge } from "@/components/Badge";
import { MetricTile } from "@/components/MetricTile";
import {
  ALERTS,
  CAUSAL_EDGES,
  CAUSAL_NODES,
  POSITIONS,
  PERSONAL_GREETING,
  SECTORS,
  type Alert,
  type CausalEdge,
  type CausalNode,
  type Position,
  type SectorData,
} from "@/data/mock";
import { Activity, ArrowRight, Gauge, Network, TrendingUp, TrendingDown, WalletCards } from "lucide-react";
import Link from "next/link";
import { cn, formatPercent } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import {
  fetchAlertsFromApi,
  fetchCausalWebGraph,
  fetchLLMUsageSummary,
  fetchPortfolioSnapshot,
  fetchSectorSnapshot,
  type LLMUsageSummary,
} from "@/lib/api";

export default function CommandCenterPage() {
  const g = PERSONAL_GREETING;
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>(ALERTS.slice(0, 3));
  const [alertTotal, setAlertTotal] = useState(ALERTS.length);
  const [positions, setPositions] = useState<Position[]>(POSITIONS);
  const [causalNodes, setCausalNodes] = useState<CausalNode[]>(CAUSAL_NODES);
  const [causalEdges, setCausalEdges] = useState<CausalEdge[]>(CAUSAL_EDGES);
  const [sectors, setSectors] = useState<SectorData[]>(SECTORS);
  const [alertSource, setAlertSource] = useState<DataSourceState>("mock");
  const [portfolioSource, setPortfolioSource] = useState<DataSourceState>("mock");
  const [causalSource, setCausalSource] = useState<DataSourceState>("fallback");
  const [sectorSource, setSectorSource] = useState<DataSourceState>("loading");
  const [llmUsage, setLlmUsage] = useState<LLMUsageSummary | null>(null);
  const { text } = useI18n();
  const totalPnl = useMemo(
    () => positions.reduce((sum, position) => sum + position.pnl, 0),
    [positions]
  );
  const activeSignals = useMemo(
    () => causalNodes.filter((node) => node.type === "signal" && node.active).length,
    [causalNodes]
  );

  useEffect(() => {
    let mounted = true;
    fetchAlertsFromApi()
      .then((alerts) => {
        if (!mounted || alerts.length === 0) return;
        setRecentAlerts(alerts.slice(0, 3));
        setAlertTotal(alerts.length);
        setAlertSource("api");
      })
      .catch(() => {
        if (mounted) setAlertSource("mock");
      });
    fetchPortfolioSnapshot()
      .then((snapshot) => {
        if (!mounted) return;
        if (snapshot.positions.length > 0) setPositions(snapshot.positions);
        setPortfolioSource(snapshot.degraded ? "partial" : "api");
      })
      .catch(() => {
        if (mounted) setPortfolioSource("mock");
      });
    fetchCausalWebGraph()
      .then((graph) => {
        if (!mounted || graph.nodes.length === 0) return;
        setCausalNodes(graph.nodes);
        setCausalEdges(graph.edges);
        setCausalSource("runtime");
      })
      .catch(() => {
        if (mounted) setCausalSource("fallback");
      });
    fetchSectorSnapshot(SECTORS)
      .then((snapshot) => {
        if (!mounted) return;
        setSectors(snapshot.sectors);
        setSectorSource(snapshot.degraded ? "partial" : "api");
      })
      .catch(() => {
        if (!mounted) return;
        setSectors(SECTORS);
        setSectorSource("mock");
      });
    fetchLLMUsageSummary()
      .then((summary) => {
        if (mounted) setLlmUsage(summary);
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      {/* Personalized greeting bar */}
      <div className="bg-gradient-to-r from-brand-emerald/10 via-bg-surface to-bg-surface border border-brand-emerald/20 rounded-sm px-5 py-4">
        <div className="text-h2 text-text-primary">
          {text(g.greeting)}
          {text("，")}
          <span className="text-brand-emerald-bright">{g.username}</span>
          {text("。")}
        </div>
        <div className="text-sm text-text-secondary mt-1">
          {text("距上次访问")} {g.hoursSinceLastVisit} {text("小时。期间发生：")}
          <span className="text-text-primary mx-1 font-mono">{g.alertsSinceLastVisit}</span> {text("条预警")} ·
          {text("其中")} <span className="text-brand-orange mx-1 font-mono">{g.alertsRelevantToPosition}</span> {text("与你持仓相关")} ·
          {text("重点：")} <span className="text-text-primary">{text(g.highlight)}</span>
        </div>
      </div>

      {/* Top row: Causal Web + Alerts */}
      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-8 p-0 overflow-hidden h-[440px] relative">
          <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
            <DataSourceBadge state={causalSource} compact />
            <Link
              href="/causal-web"
              className="flex items-center gap-1 text-caption text-text-muted hover:text-text-primary transition-colors"
            >
              {text("展开全图")}
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="px-5 pt-4">
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-brand-emerald-bright" />
              <span className="text-h3">{text("Causal Web")}</span>
              <span className="text-caption text-text-muted">{text("实时活跃因果链")}</span>
            </div>
          </div>
          <CausalWeb
            variant="preview"
            className="absolute inset-x-0 bottom-0 top-12"
            nodes={causalNodes}
            edges={causalEdges}
          />
        </Card>

        <div className="col-span-4 space-y-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <h2 className="text-h3 text-text-primary">{text("当日预警流")}</h2>
              <DataSourceBadge state={alertSource} compact />
            </div>
            <Link href="/alerts" className="text-caption text-text-muted hover:text-text-primary">
              {text("查看全部")} →
            </Link>
          </div>
          {recentAlerts.map((alert) => (
            <Card
              key={alert.id}
              variant="data"
              interactive
              className={cn(
                "border-l-[3px] cursor-pointer hover:bg-bg-surface-raised",
                alert.severity === "critical" && "border-l-data-down",
                alert.severity === "high" && "border-l-severity-high-fg",
                alert.severity === "medium" && "border-l-brand-orange"
              )}
            >
              <div className="flex items-start gap-2 mb-2">
                <Badge variant={alert.severity}>{alert.severity}</Badge>
                <span className="text-caption text-text-muted font-mono">{alert.symbol}</span>
              </div>
              <div className="text-sm text-text-primary line-clamp-2">{text(alert.title)}</div>
            </Card>
          ))}
        </div>
      </div>

      {/* Middle row: Portfolio + Sector Heatmap */}
      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-5">
          <CardHeader>
            <div>
              <CardTitle>{text("持仓概览")}</CardTitle>
              <CardSubtitle>
                {positions.length} {text("个持仓")} · {text("总浮动盈亏")}{" "}
                {totalPnl >= 0 ? "+" : ""}¥{totalPnl.toLocaleString()}
              </CardSubtitle>
            </div>
            <div className="flex items-center gap-2">
              <DataSourceBadge state={portfolioSource} compact />
              <Link href="/portfolio" className="text-caption text-text-muted hover:text-text-primary">
                {text("详情")} →
              </Link>
            </div>
          </CardHeader>
          <div className="space-y-3">
            {positions.map((pos) => {
              const isUp = pos.pnlPercent >= 0;
              return (
                <div
                  key={pos.id}
                  className="flex items-center gap-3 py-2 border-b border-border-subtle last:border-b-0"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm">{pos.symbol}</span>
                      <Badge variant={pos.direction === "long" ? "up" : "down"}>
                        {pos.direction === "long" ? text("多") : text("空")} {pos.lots} {text("手")}
                      </Badge>
                    </div>
                    <div className="text-caption text-text-muted mt-0.5">{text(pos.symbolName)}</div>
                  </div>
                  <div className="text-right">
                    <div className={cn("font-mono text-sm font-semibold tabular-nums flex items-center gap-1 justify-end", isUp ? "text-data-up" : "text-data-down")}>
                      {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                      {formatPercent(pos.pnlPercent)}
                    </div>
                    <div className="text-caption text-text-muted font-mono tabular-nums">
                      {pos.pnl > 0 ? "+" : ""}¥{pos.pnl.toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card variant="flat" className="col-span-7">
          <CardHeader>
            <div>
              <CardTitle>{text("板块热力图")}</CardTitle>
              <CardSubtitle>
                <span className="inline-flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-orange animate-heartbeat" />
                  {text("橙点 = 信号活跃")}
                </span>
              </CardSubtitle>
            </div>
            <div className="flex items-center gap-2">
              <DataSourceBadge state={sectorSource} compact />
              <Link href="/sectors" className="text-caption text-text-muted hover:text-text-primary">
                {text("详情")} →
              </Link>
            </div>
          </CardHeader>
          <SectorHeatmap sectors={sectors} />
        </Card>
      </div>

      {/* Bottom: Quick stats */}
      <div className="grid grid-cols-4 gap-5">
        <MetricTile label={text("活跃信号")} value={String(activeSignals || 0)} trend={text("实时")} caption={text("运行态图谱")} icon={Activity} tone="up" />
        <MetricTile label={text("最新预警")} value={String(alertTotal)} trend={text("最新")} caption={text("接口返回")} icon={TrendingUp} tone="warning" />
        <MetricTile label={text("校准进度")} value="73/100" caption={text("样本量")} icon={Gauge} tone="cyan" />
        <MetricTile
          label={text("LLM 月度成本")}
          value={formatUsd(llmUsage?.estimated_cost_usd)}
          caption={llmUsage ? `${llmUsage.calls} ${text("本月调用")}` : text("等待同步")}
          icon={WalletCards}
          tone="violet"
        />
      </div>
    </div>
  );
}

function formatUsd(value?: number | null): string {
  if (value == null) return "--";
  return `$${value.toFixed(2)}`;
}
