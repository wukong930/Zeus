"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { cn, formatNumber } from "@/lib/utils";

const COMMODITIES = [
  { id: "rb", name: "螺纹钢", code: "RB", currentPrice: 4310, breakeven: 4280, breakevenP90: 4480, profit: -0.7 },
  { id: "hc", name: "热卷", code: "HC", currentPrice: 3950, breakeven: 3880, breakevenP90: 4060, profit: 1.8 },
  { id: "j", name: "焦炭", code: "J", currentPrice: 2050, breakeven: 2150, breakevenP90: 2280, profit: -4.6 },
  { id: "jm", name: "焦煤", code: "JM", currentPrice: 1620, breakeven: 1650, breakevenP90: 1750, profit: -1.8 },
  { id: "i", name: "铁矿石", code: "I", currentPrice: 820, breakeven: 760, breakevenP90: 880, profit: 7.9 },
];

const COST_BREAKDOWN = [
  { component: "原料: 焦炭", value: 1100, share: 25.7 },
  { component: "原料: 铁矿石", value: 1840, share: 43.0 },
  { component: "加工费", value: 580, share: 13.5 },
  { component: "损耗+回收", value: 220, share: 5.1 },
  { component: "运输+仓储", value: 260, share: 6.1 },
  { component: "人工+水电", value: 180, share: 4.2 },
  { component: "税费", value: 100, share: 2.4 },
];

export default function IndustryLensPage() {
  const [selected, setSelected] = useState("rb");
  const commodity = COMMODITIES.find((c) => c.id === selected)!;

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Industry Lens</h1>
        <p className="text-sm text-text-secondary mt-1">
          品种成本结构 · 利润空间 · 盈亏平衡分位（P25/P50/P75/P90）
        </p>
      </div>

      <div className="flex gap-2 overflow-x-auto">
        {COMMODITIES.map((c) => (
          <button
            key={c.id}
            onClick={() => setSelected(c.id)}
            className={cn(
              "px-4 h-9 rounded-sm text-sm font-medium whitespace-nowrap border transition-colors",
              selected === c.id
                ? "bg-brand-emerald/15 border-brand-emerald text-brand-emerald-bright"
                : "border-border-default text-text-secondary hover:bg-bg-surface-raised"
            )}
          >
            <span className="font-mono mr-2">{c.code}</span>
            {c.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-12 gap-5">
        {/* Cost waterfall */}
        <Card variant="flat" className="col-span-7">
          <CardHeader>
            <div>
              <CardTitle>成本分解 — {commodity.name}</CardTitle>
              <CardSubtitle>每吨单位成本（公开数据 + LLM 提取，误差 ±5%）</CardSubtitle>
            </div>
          </CardHeader>
          <div className="space-y-2">
            {COST_BREAKDOWN.map((item) => (
              <div key={item.component} className="flex items-center gap-3">
                <div className="w-32 text-sm text-text-secondary shrink-0">{item.component}</div>
                <div className="flex-1 h-6 bg-bg-base rounded-sm relative overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-brand-emerald/30 to-brand-emerald/60"
                    style={{ width: `${item.share * 2}%` }}
                  />
                  <div className="absolute inset-0 flex items-center justify-end pr-2">
                    <span className="text-caption font-mono tabular-nums">{item.share}%</span>
                  </div>
                </div>
                <div className="w-20 text-right font-mono text-sm tabular-nums">
                  ¥{item.value.toLocaleString()}
                </div>
              </div>
            ))}
            <div className="border-t border-border-default pt-3 mt-3 flex items-center gap-3">
              <div className="w-32 text-h3 text-text-primary shrink-0">单位成本</div>
              <div className="flex-1" />
              <div className="text-h2 font-mono tabular-nums text-text-primary">
                ¥{COST_BREAKDOWN.reduce((s, c) => s + c.value, 0).toLocaleString()}
              </div>
            </div>
          </div>

          <div className="mt-4 text-caption text-text-muted leading-relaxed">
            数据来源：交易所公开 · 统计局 · 行业协会报告 · LLM 提取自财联社
          </div>
        </Card>

        {/* Cost curve quantiles */}
        <Card variant="flat" className="col-span-5">
          <CardHeader>
            <div>
              <CardTitle>成本曲线分位数</CardTitle>
              <CardSubtitle>边际成本决定价格地板，不是平均成本</CardSubtitle>
            </div>
          </CardHeader>
          <CostQuantileChart commodity={commodity} />
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-5">
        <Card variant="flat">
          <div className="text-caption text-text-muted uppercase mb-2">当前价格</div>
          <div className="text-display font-mono text-text-primary tabular-nums leading-none">
            ¥{commodity.currentPrice.toLocaleString()}
          </div>
          <div className={cn("text-sm font-mono mt-2 tabular-nums", commodity.profit >= 0 ? "text-data-up" : "text-data-down")}>
            利润率 {commodity.profit >= 0 ? "+" : ""}{commodity.profit}%
          </div>
        </Card>
        <Card variant="flat">
          <div className="text-caption text-text-muted uppercase mb-2">P75 边际成本</div>
          <div className="text-display font-mono text-text-primary tabular-nums leading-none">
            ¥{commodity.breakeven.toLocaleString()}
          </div>
          <div className="text-sm text-text-muted mt-2">
            前 25% 高成本产能盈亏平衡
          </div>
        </Card>
        <Card variant="flat">
          <div className="text-caption text-text-muted uppercase mb-2">P90 边际成本</div>
          <div className="text-display font-mono text-text-primary tabular-nums leading-none">
            ¥{commodity.breakevenP90.toLocaleString()}
          </div>
          <div className="text-sm text-text-muted mt-2">
            前 10% 高成本产能盈亏平衡
          </div>
        </Card>
      </div>

      {/* Cost-driven signal triggers */}
      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>成本信号触发条件</CardTitle>
            <CardSubtitle>价格触及关键分位时自动注入信号系统</CardSubtitle>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-3">
          {[
            { condition: "价格跌破 P50 中位数", trigger: "median_pressure 信号", active: false },
            { condition: "价格跌破 P75 边际", trigger: "marginal_capacity_squeeze 信号", active: commodity.id === "rb" },
            { condition: "价格跌破 P90 边际", trigger: "capacity_contraction 信号", active: commodity.id === "j" },
            { condition: "利润率 < -5% 持续 2 周", trigger: "capacity_contraction_persistent", active: false },
            { condition: "利润率由负转正", trigger: "restart_expectation 信号", active: false },
            { condition: "成本 / 价格剪刀差扩大", trigger: "cost_squeeze 信号", active: false },
          ].map((rule, i) => (
            <div
              key={i}
              className={cn(
                "flex items-center gap-3 p-3 rounded-sm border",
                rule.active ? "bg-brand-orange/10 border-brand-orange" : "bg-bg-base border-border-subtle"
              )}
            >
              <div
                className={cn(
                  "w-2 h-2 rounded-full",
                  rule.active ? "bg-brand-orange animate-heartbeat" : "bg-text-disabled"
                )}
              />
              <div className="flex-1">
                <div className="text-sm text-text-primary">{rule.condition}</div>
                <div className="text-caption text-text-muted font-mono">→ {rule.trigger}</div>
              </div>
              {rule.active && <Badge variant="orange">已触发</Badge>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function CostQuantileChart({ commodity }: { commodity: typeof COMMODITIES[number] }) {
  const quantiles = [
    { p: "P25", value: commodity.breakeven * 0.85, label: "低成本" },
    { p: "P50", value: commodity.breakeven * 0.94, label: "中位数" },
    { p: "P75", value: commodity.breakeven, label: "高成本" },
    { p: "P90", value: commodity.breakevenP90, label: "边际产能" },
  ];

  const min = quantiles[0].value * 0.95;
  const max = quantiles[3].value * 1.08;
  const norm = (v: number) => ((v - min) / (max - min)) * 100;

  return (
    <div className="space-y-3 py-3">
      <div className="relative h-32 bg-bg-base rounded-sm">
        {/* Cumulative cost curve illustration */}
        <svg viewBox="0 0 200 100" className="w-full h-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10B981" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path
            d="M 0 90 C 30 88 50 80 80 65 C 110 50 140 30 200 10 L 200 100 L 0 100 Z"
            fill="url(#curveGrad)"
          />
          <path
            d="M 0 90 C 30 88 50 80 80 65 C 110 50 140 30 200 10"
            fill="none"
            stroke="#10B981"
            strokeWidth="1.5"
          />
          {/* Current price line */}
          <line
            x1={norm(commodity.currentPrice) * 2}
            y1="0"
            x2={norm(commodity.currentPrice) * 2}
            y2="100"
            stroke="#F97316"
            strokeWidth="1.5"
            strokeDasharray="3 2"
          />
        </svg>
        <div
          className="absolute top-1 -translate-x-1/2"
          style={{ left: `${norm(commodity.currentPrice)}%` }}
        >
          <Badge variant="orange">当前 ¥{formatNumber(commodity.currentPrice, { decimals: 0 })}</Badge>
        </div>
      </div>
      <div className="space-y-1.5">
        {quantiles.map((q) => {
          const breached = commodity.currentPrice < q.value;
          return (
            <div key={q.p} className="flex items-center gap-2 text-sm">
              <div className="w-12 font-mono text-text-muted">{q.p}</div>
              <div className="flex-1 h-1.5 bg-bg-surface-raised rounded-full relative">
                <div
                  className="absolute top-0 left-0 h-full bg-brand-emerald rounded-full"
                  style={{ width: `${norm(q.value)}%` }}
                />
                <div
                  className="absolute top-0 w-0.5 h-full bg-brand-orange"
                  style={{ left: `${norm(commodity.currentPrice)}%` }}
                />
              </div>
              <div className="w-20 text-right font-mono tabular-nums text-text-primary">¥{formatNumber(q.value, { decimals: 0 })}</div>
              {breached && <Badge variant="critical">突破</Badge>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
