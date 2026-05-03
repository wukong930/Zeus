"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { VintageBadge } from "@/components/VintageBadge";
import { POSITIONS } from "@/data/mock";
import { fetchPortfolioSnapshot, type PortfolioSnapshot, type PortfolioPosition } from "@/lib/api";
import { Plus, TrendingUp, TrendingDown, AlertTriangle, RefreshCw } from "lucide-react";
import { cn, formatPercent } from "@/lib/utils";

export default function PortfolioPage() {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [source, setSource] = useState<"loading" | "api" | "mock">("loading");

  useEffect(() => {
    let ignore = false;
    fetchPortfolioSnapshot()
      .then((data) => {
        if (!ignore) {
          setSnapshot(data);
          setPositions(data.positions);
          setSource("api");
        }
      })
      .catch(() => {
        if (!ignore) {
          setSnapshot(null);
          setPositions(mockPositions());
          setSource("mock");
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const totalPnL = useMemo(() => positions.reduce((sum, p) => sum + p.pnl, 0), [positions]);
  const totalMargin = useMemo(() => positions.reduce((sum, p) => sum + p.marginUsed, 0), [positions]);
  const totalEquity = 100000;
  const usage = (totalMargin / totalEquity) * 100;
  const worstStress = useMemo(
    () =>
      snapshot?.stressResults.reduce(
        (worst, result) => Math.min(worst, result.portfolio_pnl),
        0
      ) ?? 0,
    [snapshot]
  );

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">Portfolio Map</h1>
          <p className="text-sm text-text-secondary mt-1">
            可视化展示持仓在传导图中的位置 + 组合风险
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={source === "mock" ? "orange" : "emerald"}>
            {source === "loading" ? "SYNC" : source.toUpperCase()}
          </Badge>
          <Button variant="action">
            <Plus className="w-4 h-4" />
            添加持仓
          </Button>
        </div>
      </div>

      {/* Risk dashboard */}
      <div className="grid grid-cols-4 gap-5">
        <RiskCard
          label="组合 P&L"
          value={`${totalPnL >= 0 ? "+" : ""}¥${totalPnL.toLocaleString()}`}
          subtext="当日浮动"
          colorClass={totalPnL >= 0 ? "text-data-up" : "text-data-down"}
        />
        <RiskCard
          label="VaR 95%"
          value={`¥${formatCurrency(snapshot?.varResult?.var95 ?? 0)}`}
          subtext={`${snapshot?.varResult?.horizon ?? 1} 日 95% 置信`}
          colorClass="text-text-primary"
        />
        <RiskCard label="保证金占用" value={`${usage.toFixed(1)}%`} subtext={`¥${totalMargin.toLocaleString()} / ¥${totalEquity.toLocaleString()}`} colorClass="text-brand-emerald-bright" />
        <RiskCard
          label="压力损失"
          value={`¥${formatCurrency(worstStress)}`}
          subtext={`${snapshot?.stressResults.length ?? 0} 个场景`}
          colorClass={worstStress < 0 ? "text-severity-high-fg" : "text-text-primary"}
        />
      </div>

      {/* Position list */}
      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>持仓列表</CardTitle>
            <CardSubtitle>{positions.length} 笔持仓 · 包含传导图激活范围</CardSubtitle>
          </div>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-caption text-text-muted border-b border-border-subtle">
                <th className="text-left py-2 px-3 font-medium">品种</th>
                <th className="text-left py-2 px-3 font-medium">方向</th>
                <th className="text-right py-2 px-3 font-medium">手数</th>
                <th className="text-right py-2 px-3 font-medium">入场均价</th>
                <th className="text-right py-2 px-3 font-medium">现价</th>
                <th className="text-right py-2 px-3 font-medium">浮动盈亏</th>
                <th className="text-right py-2 px-3 font-medium">收益率</th>
                <th className="text-left py-2 px-3 font-medium">数据版本</th>
                <th className="text-left py-2 px-3 font-medium">开仓日期</th>
                <th className="text-right py-2 px-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const isUp = pos.pnlPercent >= 0;
                return (
                  <tr key={pos.id} className="border-b border-border-subtle hover:bg-bg-surface-raised">
                    <td className="py-3 px-3">
                      <div>
                        <div className="font-mono">{pos.symbol}</div>
                        <div className="text-caption text-text-muted">{pos.symbolName}</div>
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <Badge variant={pos.direction === "long" ? "up" : "down"}>
                        {pos.direction === "long" ? "做多" : "做空"}
                      </Badge>
                    </td>
                    <td className="py-3 px-3 text-right font-mono tabular-nums">{pos.lots}</td>
                    <td className="py-3 px-3 text-right font-mono tabular-nums">{pos.avgEntry.toLocaleString()}</td>
                    <td className="py-3 px-3 text-right font-mono tabular-nums">{pos.currentPrice.toLocaleString()}</td>
                    <td className={cn("py-3 px-3 text-right font-mono tabular-nums font-semibold", isUp ? "text-data-up" : "text-data-down")}>
                      {pos.pnl >= 0 ? "+" : ""}¥{pos.pnl.toLocaleString()}
                    </td>
                    <td className={cn("py-3 px-3 text-right font-mono tabular-nums font-semibold", isUp ? "text-data-up" : "text-data-down")}>
                      <span className="inline-flex items-center gap-1">
                        {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {formatPercent(pos.pnlPercent)}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <VintageBadge vintageAt={pos.vintageAt} />
                    </td>
                    <td className="py-3 px-3 text-text-muted">{pos.openDate}</td>
                    <td className="py-3 px-3 text-right space-x-1">
                      <Button variant="ghost" size="sm">减半</Button>
                      <Button variant="ghost" size="sm">平仓</Button>
                    </td>
                  </tr>
                );
              })}
              {positions.length === 0 && (
                <tr>
                  <td colSpan={10} className="py-10 text-center text-text-muted">
                    {source === "loading" ? (
                      <span className="inline-flex items-center gap-2">
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        持仓加载中
                      </span>
                    ) : (
                      "当前没有开放持仓"
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Propagation activation map */}
      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>传导图激活范围</CardTitle>
            <CardSubtitle>持仓自动激活的关联品种监控</CardSubtitle>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-5">
          {positions.length > 0 ? (
            positions.slice(0, 2).map((position) => (
              <PropagationGroup
                key={position.id}
                anchor={`${position.symbol} (持仓)`}
                sector={position.sector}
                related={relatedForSector(position.sector)}
              />
            ))
          ) : (
            <div className="col-span-2 text-sm text-text-muted py-4">
              暂无开放持仓，传导图保持待机。
            </div>
          )}
        </div>
      </Card>

      {/* Warnings */}
      <Card variant="flat" className="border-l-[3px] border-l-severity-high-fg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-severity-high-fg shrink-0 mt-0.5" />
          <div>
            <div className="text-h3 text-text-primary">板块集中度提示</div>
            <p className="text-sm text-text-secondary mt-1">
              当前保证金占用 {usage.toFixed(1)}%。高相关或高占用持仓会在建议生成时降级。
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}

function mockPositions(): PortfolioPosition[] {
  return POSITIONS.map((position) => ({
    ...position,
    marginUsed: position.lots * position.currentPrice * 0.1,
    status: "open",
  }));
}

function formatCurrency(value: number) {
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: 0,
  });
}

function relatedForSector(sector: string) {
  if (sector === "rubber") {
    return [
      { symbol: "RU", name: "天然橡胶", reason: "替代品", lag: "0-2d" },
      { symbol: "BR", name: "顺丁橡胶", reason: "下游替代", lag: "5-15d" },
    ];
  }

  if (sector === "energy") {
    return [
      { symbol: "SC", name: "原油", reason: "链路锚点", lag: "0-1d" },
      { symbol: "TA", name: "PTA", reason: "下游化工", lag: "1-5d" },
    ];
  }

  return [
    { symbol: "I", name: "铁矿石", reason: "上游原料", lag: "0-3d" },
    { symbol: "J", name: "焦炭", reason: "上游原料", lag: "0-3d" },
    { symbol: "JM", name: "焦煤", reason: "二级原料", lag: "3-7d" },
    { symbol: "HC", name: "热卷", reason: "替代品", lag: "0-1d" },
  ];
}

function RiskCard({
  label,
  value,
  subtext,
  colorClass,
}: {
  label: string;
  value: string;
  subtext: string;
  colorClass: string;
}) {
  return (
    <Card variant="flat">
      <div className="text-caption text-text-muted uppercase tracking-wider">{label}</div>
      <div className={cn("text-display font-mono mt-2 leading-none tabular-nums", colorClass)}>{value}</div>
      <div className="text-caption text-text-muted mt-2">{subtext}</div>
    </Card>
  );
}

function PropagationGroup({
  anchor,
  sector,
  related,
}: {
  anchor: string;
  sector: string;
  related: { symbol: string; name: string; reason: string; lag: string }[];
}) {
  return (
    <div className="bg-bg-base rounded-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full bg-brand-emerald-bright animate-heartbeat" />
        <span className="font-mono text-sm">{anchor}</span>
        <Badge variant="emerald">{sector}</Badge>
      </div>
      <div className="text-caption text-text-muted mb-2">激活监控品种 ({related.length})</div>
      <div className="space-y-1.5">
        {related.map((r) => (
          <div key={r.symbol} className="flex items-center justify-between text-xs py-1 px-2 bg-bg-surface rounded-xs">
            <div className="flex items-center gap-2">
              <span className="font-mono text-text-primary">{r.symbol}</span>
              <span className="text-text-muted">{r.name}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-text-muted">{r.reason}</span>
              <span className="text-text-muted font-mono">{r.lag}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
