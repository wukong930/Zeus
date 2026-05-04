"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { CausalWeb } from "@/components/CausalWeb";
import { SectorHeatmap } from "@/components/SectorHeatmap";
import { AlertCard } from "@/components/AlertCard";
import { Badge } from "@/components/Badge";
import { MetricTile } from "@/components/MetricTile";
import { ALERTS, POSITIONS, PERSONAL_GREETING } from "@/data/mock";
import { Activity, ArrowRight, Gauge, Network, TrendingUp, TrendingDown, WalletCards } from "lucide-react";
import Link from "next/link";
import { cn, formatPercent } from "@/lib/utils";

export default function CommandCenterPage() {
  const g = PERSONAL_GREETING;
  const recentAlerts = ALERTS.slice(0, 3);

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      {/* Personalized greeting bar */}
      <div className="bg-gradient-to-r from-brand-emerald/10 via-bg-surface to-bg-surface border border-brand-emerald/20 rounded-sm px-5 py-4">
        <div className="text-h2 text-text-primary">
          {g.greeting}，<span className="text-brand-emerald-bright">{g.username}</span>。
        </div>
        <div className="text-sm text-text-secondary mt-1">
          距上次访问 {g.hoursSinceLastVisit} 小时。期间发生：
          <span className="text-text-primary mx-1 font-mono">{g.alertsSinceLastVisit}</span> 条预警 ·
          其中 <span className="text-brand-orange mx-1 font-mono">{g.alertsRelevantToPosition}</span> 与你持仓相关 ·
          重点：<span className="text-text-primary">{g.highlight}</span>
        </div>
      </div>

      {/* Top row: Causal Web + Alerts */}
      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-8 p-0 overflow-hidden h-[440px] relative">
          <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
            <Badge variant="emerald">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-emerald-bright animate-heartbeat" />
              Live
            </Badge>
            <Link
              href="/causal-web"
              className="flex items-center gap-1 text-caption text-text-muted hover:text-text-primary transition-colors"
            >
              展开全图
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          <div className="px-5 pt-4">
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-brand-emerald-bright" />
              <span className="text-h3">Causal Web</span>
              <span className="text-caption text-text-muted">实时活跃因果链</span>
            </div>
          </div>
          <CausalWeb variant="preview" className="absolute inset-0 top-12" />
        </Card>

        <div className="col-span-4 space-y-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-h3 text-text-primary">当日预警流</h2>
            <Link href="/alerts" className="text-caption text-text-muted hover:text-text-primary">
              查看全部 →
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
              <div className="text-sm text-text-primary line-clamp-2">{alert.title}</div>
            </Card>
          ))}
        </div>
      </div>

      {/* Middle row: Portfolio + Sector Heatmap */}
      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-5">
          <CardHeader>
            <div>
              <CardTitle>持仓概览</CardTitle>
              <CardSubtitle>{POSITIONS.length} 个持仓 · 总浮动盈亏 +¥8,300</CardSubtitle>
            </div>
            <Link href="/portfolio" className="text-caption text-text-muted hover:text-text-primary">
              详情 →
            </Link>
          </CardHeader>
          <div className="space-y-3">
            {POSITIONS.map((pos) => {
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
                        {pos.direction === "long" ? "多" : "空"} {pos.lots} 手
                      </Badge>
                    </div>
                    <div className="text-caption text-text-muted mt-0.5">{pos.symbolName}</div>
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
              <CardTitle>板块热力图</CardTitle>
              <CardSubtitle>
                <span className="inline-flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-orange animate-heartbeat" />
                  橙点 = 信号活跃
                </span>
              </CardSubtitle>
            </div>
            <Link href="/sectors" className="text-caption text-text-muted hover:text-text-primary">
              详情 →
            </Link>
          </CardHeader>
          <SectorHeatmap />
        </Card>
      </div>

      {/* Bottom: Quick stats */}
      <div className="grid grid-cols-4 gap-5">
        <MetricTile label="活跃信号" value="17" trend="+3" caption="过去 24h" icon={Activity} tone="up" />
        <MetricTile label="本月预警" value="142" trend="+8.2%" caption="vs 上月" icon={TrendingUp} tone="warning" />
        <MetricTile label="校准进度" value="73/100" caption="样本量" icon={Gauge} tone="cyan" />
        <MetricTile label="LLM 月度成本" value="$24.30" caption="预算 $80" icon={WalletCards} tone="violet" />
      </div>
    </div>
  );
}
