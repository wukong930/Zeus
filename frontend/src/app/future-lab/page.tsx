"use client";

import { useState } from "react";
import { AlertTriangle, Beaker, Play, Sparkles } from "lucide-react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { runScenarioSimulation, type ScenarioReport } from "@/lib/api";
import { cn } from "@/lib/utils";

const SCENARIO_PRESETS = [
  {
    label: "20号胶 / 橡胶链",
    targetSymbol: "RU",
    basePrice: 15400,
    volatilityPct: 2.1,
    shocks: [
      { symbol: "NR", label: "NR 原料冲击", min: -20, max: 20, value: 6 },
      { symbol: "BR", label: "BR 替代品", min: -15, max: 15, value: 0 },
      { symbol: "RU", label: "RU 盘面冲击", min: -15, max: 15, value: 0 },
    ],
  },
  {
    label: "螺纹钢 / 黑色链",
    targetSymbol: "RB",
    basePrice: 3250,
    volatilityPct: 1.8,
    shocks: [
      { symbol: "I", label: "铁矿石", min: -20, max: 20, value: 10 },
      { symbol: "J", label: "焦炭", min: -15, max: 15, value: -5 },
      { symbol: "JM", label: "焦煤", min: -15, max: 15, value: 0 },
    ],
  },
  {
    label: "原油 / 能化链",
    targetSymbol: "TA",
    basePrice: 5860,
    volatilityPct: 2.0,
    shocks: [
      { symbol: "SC", label: "原油", min: -20, max: 20, value: 8 },
      { symbol: "FU", label: "燃料油", min: -15, max: 15, value: 0 },
      { symbol: "EG", label: "乙二醇", min: -15, max: 15, value: -2 },
    ],
  },
];

export default function FutureLabPage() {
  const [presetIndex, setPresetIndex] = useState(0);
  const preset = SCENARIO_PRESETS[presetIndex];
  const [shockValues, setShockValues] = useState<Record<string, number>>(
    valuesFromPreset(SCENARIO_PRESETS[0])
  );
  const [simulations, setSimulations] = useState(1000);
  const [days, setDays] = useState(20);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<ScenarioReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await runScenarioSimulation({
        target_symbol: preset.targetSymbol,
        base_price: preset.basePrice,
        shocks: Object.fromEntries(
          Object.entries(shockValues).map(([symbol, value]) => [symbol, value / 100])
        ),
        days,
        simulations,
        volatility_pct: preset.volatilityPct / 100,
        seed: 7,
        max_depth: 3,
      });
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "scenario simulation failed");
    } finally {
      setRunning(false);
    }
  };

  const updatePreset = (index: number) => {
    setPresetIndex(index);
    setShockValues(valuesFromPreset(SCENARIO_PRESETS[index]));
    setReport(null);
    setError(null);
  };

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Future Lab</h1>
        <p className="text-sm text-text-secondary mt-1">
          Monte Carlo 价格路径模拟 + What-if 假设检验
        </p>
      </div>

      <div className="grid grid-cols-12 gap-5">
        <Card variant="flat" className="col-span-12 xl:col-span-4 space-y-4">
          <CardHeader>
            <CardTitle>场景配置</CardTitle>
          </CardHeader>

          <div>
            <label className="text-caption text-text-muted block mb-2">目标链条</label>
            <select
              value={presetIndex}
              onChange={(event) => updatePreset(Number(event.target.value))}
              className="w-full bg-bg-base border border-border-default rounded-sm h-9 px-3 text-sm focus:border-brand-emerald focus:outline-none"
            >
              {SCENARIO_PRESETS.map((item, index) => (
                <option key={item.targetSymbol} value={index}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-caption text-text-muted block mb-2">假设条件</label>
            <div className="space-y-2">
              {preset.shocks.map((shock) => (
                <ScenarioSlider
                  key={shock.symbol}
                  label={shock.label}
                  min={shock.min}
                  max={shock.max}
                  value={shockValues[shock.symbol] ?? shock.value}
                  suffix="%"
                  onChange={(value) =>
                    setShockValues((current) => ({ ...current, [shock.symbol]: value }))
                  }
                />
              ))}
            </div>
          </div>

          <div>
            <label className="text-caption text-text-muted block mb-2">模拟参数</label>
            <div className="space-y-2">
              <ScenarioSlider
                label="模拟次数"
                min={100}
                max={5000}
                step={100}
                value={simulations}
                suffix=""
                tone="neutral"
                onChange={setSimulations}
              />
              <ScenarioSlider
                label="时间跨度"
                min={5}
                max={60}
                value={days}
                suffix=" 天"
                tone="neutral"
                onChange={setDays}
              />
            </div>
          </div>

          <Button variant="action" className="w-full" onClick={run} disabled={running}>
            {running ? (
              <>
                <Sparkles className="w-4 h-4 animate-spin-slow" />
                正在推演
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                运行推演
              </>
            )}
          </Button>

          {error && (
            <div className="flex items-start gap-2 text-sm text-data-down">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </Card>

        <Card variant="flat" className="col-span-12 xl:col-span-8">
          <CardHeader>
            <div className="flex items-center gap-3">
              <CardTitle>概率扇</CardTitle>
              {report && <Badge variant="emerald">推演完成</Badge>}
            </div>
            <CardSubtitle>
              {preset.targetSymbol} 未来 {days} 天价格路径分布（{simulations} 次模拟）
            </CardSubtitle>
          </CardHeader>

          {running ? (
            <div className="h-80 flex items-center justify-center">
              <div className="text-center space-y-3">
                <Beaker className="w-12 h-12 text-brand-emerald-bright mx-auto animate-pulse" />
                <div className="text-text-secondary">正在沿传导图模拟价格路径</div>
                <div className="w-48 mx-auto h-1 bg-bg-surface-raised rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-emerald animate-shimmer"
                    style={{
                      background:
                        "linear-gradient(90deg, #059669 0%, #10B981 50%, #059669 100%)",
                      backgroundSize: "200% 100%",
                    }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <ProbabilityFan report={report} basePrice={preset.basePrice} />
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
            <ScenarioStat
              label="P5 下行风险"
              value={report ? `< ${price(report.monte_carlo.terminal_distribution.p5)}` : "-"}
              desc="5% 分位"
              colorClass="text-data-down"
            />
            <ScenarioStat
              label="P50 中位数路径"
              value={report ? price(report.monte_carlo.terminal_distribution.p50) : "-"}
              desc="预期价格"
              colorClass="text-text-primary"
            />
            <ScenarioStat
              label="P95 上行"
              value={report ? `> ${price(report.monte_carlo.terminal_distribution.p95)}` : "-"}
              desc="95% 分位"
              colorClass="text-data-up"
            />
          </div>
        </Card>
      </div>

      {report && (
        <Card variant="flat">
          <CardHeader>
            <div>
              <CardTitle>情景叙事</CardTitle>
              <CardSubtitle>
                冲击 {formatPct(report.monte_carlo.applied_shock)}，跌破基准概率{" "}
                {formatPct(report.monte_carlo.downside_probability, false)}
              </CardSubtitle>
            </div>
          </CardHeader>
          <div className="text-sm text-text-secondary leading-relaxed space-y-4">
            <p>{report.narrative}</p>
            <PathGraph report={report} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="text-caption text-text-muted">关键风险</div>
                {report.risk_points.map((item) => (
                  <div key={item} className="bg-bg-base rounded-sm p-3">
                    {item}
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <div className="text-caption text-text-muted">建议动作</div>
                {report.suggested_actions.map((item) => (
                  <div key={item} className="bg-bg-base rounded-sm p-3">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function PathGraph({ report }: { report: ScenarioReport }) {
  const paths = report.what_if.key_paths.slice(0, 4);
  if (paths.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="text-caption text-text-muted">传导路径</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {paths.map((path) => (
          <div
            key={`${path.root_symbol}-${path.source_symbol}-${path.target_symbol}-${path.depth}`}
            className="bg-bg-base rounded-sm p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 font-mono text-text-primary">
                <span>{path.source_symbol}</span>
                <span className="text-text-muted">→</span>
                <span>{path.target_symbol}</span>
              </div>
              <span
                className={cn(
                  "font-mono tabular-nums",
                  path.impact >= 0 ? "text-data-up" : "text-data-down"
                )}
              >
                {formatPct(path.impact)}
              </span>
            </div>
            <div className="text-caption text-text-muted mt-2">
              {path.relationship}，滞后 {path.lag_days} 天
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScenarioSlider({
  label,
  min,
  max,
  step = 1,
  value,
  suffix,
  tone = "signed",
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  suffix: string;
  tone?: "signed" | "neutral";
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-caption mb-1">
        <span className="text-text-muted">{label}</span>
        <span
          className={cn(
            "font-mono tabular-nums",
            tone === "neutral"
              ? "text-text-primary"
              : value >= 0
                ? "text-data-up"
                : "text-data-down"
          )}
        >
          {tone === "signed" && value >= 0 ? "+" : ""}
          {value}
          {suffix}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full h-1 bg-bg-surface-raised rounded-full appearance-none cursor-pointer accent-brand-emerald"
      />
    </div>
  );
}

function ScenarioStat({
  label,
  value,
  desc,
  colorClass,
}: {
  label: string;
  value: string;
  desc: string;
  colorClass: string;
}) {
  return (
    <div className="bg-bg-base rounded-sm p-3 min-h-24">
      <div className="text-caption text-text-muted">{label}</div>
      <div className={cn("text-h2 font-mono tabular-nums mt-1 break-words", colorClass)}>
        {value}
      </div>
      <div className="text-caption text-text-muted mt-1">{desc}</div>
    </div>
  );
}

function ProbabilityFan({ report, basePrice }: { report: ScenarioReport | null; basePrice: number }) {
  if (!report) {
    return (
      <div className="h-80 flex items-center justify-center text-sm text-text-muted">
        配置场景后运行推演
      </div>
    );
  }

  const distribution = report.monte_carlo.terminal_distribution;
  const values = [
    basePrice,
    distribution.p5,
    distribution.p25,
    distribution.p50,
    distribution.p75,
    distribution.p95,
  ];
  const min = Math.min(...values) * 0.98;
  const max = Math.max(...values) * 1.02;
  const yFor = (value: number) => 286 - ((value - min) / (max - min || 1)) * 252;
  const baseY = yFor(basePrice);
  const y5 = yFor(distribution.p5);
  const y25 = yFor(distribution.p25);
  const y50 = yFor(distribution.p50);
  const y75 = yFor(distribution.p75);
  const y95 = yFor(distribution.p95);

  return (
    <div className="h-80 relative">
      <svg viewBox="0 0 800 320" className="w-full h-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="fanGrad95" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#F97316" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#F97316" stopOpacity="0.05" />
          </linearGradient>
          <linearGradient id="fanGrad75" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.15" />
          </linearGradient>
        </defs>
        {[80, 160, 240].map((y) => (
          <line key={y} x1="0" y1={y} x2="800" y2={y} stroke="#1A1A1A" strokeWidth="0.5" />
        ))}
        <line
          x1="300"
          y1="0"
          x2="300"
          y2="320"
          stroke="#404040"
          strokeWidth="1"
          strokeDasharray="3 2"
        />
        <path
          d={`M 0 ${baseY + 28} L 60 ${baseY + 20} L 120 ${baseY + 24} L 180 ${baseY + 8} L 240 ${baseY + 4} L 300 ${baseY}`}
          fill="none"
          stroke="#A3A3A3"
          strokeWidth="1.5"
        />
        <path d={`M 300 ${baseY} L 800 ${y95} L 800 ${y5} L 300 ${baseY} Z`} fill="url(#fanGrad95)" />
        <path d={`M 300 ${baseY} L 800 ${y75} L 800 ${y25} L 300 ${baseY} Z`} fill="url(#fanGrad75)" />
        <path d={`M 300 ${baseY} L 800 ${y50}`} fill="none" stroke="#10B981" strokeWidth="2" />
        <circle cx="300" cy={baseY} r="5" fill="#F97316" />
        <circle cx="300" cy={baseY} r="10" fill="#F97316" fillOpacity="0.3" />
        <text x="780" y={Math.max(18, y95 + 5)} textAnchor="end" className="text-[10px] fill-data-up font-mono">
          P95 {price(distribution.p95)}
        </text>
        <text x="780" y={y50 + 5} textAnchor="end" className="text-[10px] fill-text-primary font-mono">
          P50 {price(distribution.p50)}
        </text>
        <text x="780" y={Math.min(306, y5 + 5)} textAnchor="end" className="text-[10px] fill-data-down font-mono">
          P5 {price(distribution.p5)}
        </text>
      </svg>
    </div>
  );
}

function valuesFromPreset(preset: (typeof SCENARIO_PRESETS)[number]): Record<string, number> {
  return Object.fromEntries(preset.shocks.map((shock) => [shock.symbol, shock.value]));
}

function price(value: number): string {
  return Math.round(value).toLocaleString("zh-CN");
}

function formatPct(value: number, signed = true): string {
  const prefix = signed && value >= 0 ? "+" : "";
  return `${prefix}${(value * 100).toFixed(1)}%`;
}
