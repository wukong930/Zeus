"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
import { Beaker, Play, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export default function FutureLabPage() {
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(true);

  const run = () => {
    setRunning(true);
    setDone(false);
    setTimeout(() => {
      setRunning(false);
      setDone(true);
    }, 2200);
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
        <Card variant="flat" className="col-span-4 space-y-4">
          <CardHeader>
            <CardTitle>场景配置</CardTitle>
          </CardHeader>

          <div>
            <label className="text-caption text-text-muted block mb-2">目标品种</label>
            <select className="w-full bg-bg-base border border-border-default rounded-sm h-9 px-3 text-sm focus:border-brand-emerald focus:outline-none">
              <option>螺纹钢 RB2510</option>
              <option>20号胶 NR2509</option>
              <option>沪铜 CU2502</option>
            </select>
          </div>

          <div>
            <label className="text-caption text-text-muted block mb-2">假设条件</label>
            <div className="space-y-2">
              <ScenarioSlider label="铁矿石变动" min={-20} max={20} default_={10} />
              <ScenarioSlider label="焦煤变动" min={-15} max={15} default_={-5} />
              <ScenarioSlider label="终端需求" min={-30} max={30} default_={0} />
            </div>
          </div>

          <div>
            <label className="text-caption text-text-muted block mb-2">模拟参数</label>
            <div className="space-y-2">
              <ScenarioSlider label="模拟次数" min={100} max={5000} default_={1000} />
              <ScenarioSlider label="时间跨度（天）" min={5} max={60} default_={20} />
            </div>
          </div>

          <Button variant="action" className="w-full" onClick={run} disabled={running}>
            {running ? (
              <>
                <Sparkles className="w-4 h-4 animate-spin-slow" />
                Lab is brewing...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                运行推演
              </>
            )}
          </Button>
        </Card>

        <Card variant="flat" className="col-span-8">
          <CardHeader>
            <div className="flex items-center gap-3">
              <CardTitle>概率扇</CardTitle>
              {done && <Badge variant="emerald">推演完成</Badge>}
            </div>
            <CardSubtitle>未来 20 天 RB2510 价格路径分布（1000 次模拟）</CardSubtitle>
          </CardHeader>

          {running ? (
            <div className="h-80 flex items-center justify-center">
              <div className="text-center space-y-3">
                <Beaker className="w-12 h-12 text-brand-emerald-bright mx-auto animate-pulse" />
                <div className="text-text-secondary">正在沿传导图模拟价格路径...</div>
                <div className="w-48 mx-auto h-1 bg-bg-surface-raised rounded-full overflow-hidden">
                  <div className="h-full bg-brand-emerald animate-shimmer" style={{ background: "linear-gradient(90deg, #059669 0%, #10B981 50%, #059669 100%)", backgroundSize: "200% 100%" }} />
                </div>
              </div>
            </div>
          ) : (
            <ProbabilityFan />
          )}

          {done && (
            <div className="grid grid-cols-3 gap-3 mt-5">
              <ScenarioStat label="P5 下行风险" value="< 4080" desc="5% 概率破" colorClass="text-data-down" />
              <ScenarioStat label="P50 中位数路径" value="4380" desc="预期价格" colorClass="text-text-primary" />
              <ScenarioStat label="P95 上行" value="> 4720" desc="5% 概率破" colorClass="text-data-up" />
            </div>
          )}
        </Card>
      </div>

      {done && (
        <Card variant="flat">
          <CardHeader>
            <div>
              <CardTitle>LLM 情景叙事</CardTitle>
              <CardSubtitle>由 Claude Sonnet 4.6 生成的可读分析</CardSubtitle>
            </div>
          </CardHeader>
          <div className="text-sm text-text-secondary leading-relaxed space-y-3">
            <p>
              基于当前假设（<span className="text-data-up">铁矿 +10%</span>、<span className="text-data-down">焦煤 -5%</span>、<span className="text-text-primary">终端需求持平</span>），1000 次模拟显示螺纹钢未来 20 天价格分布偏正态。
            </p>
            <p>
              <strong className="text-text-primary">核心驱动</strong>：铁矿走强直接推升钢厂成本（弹性 0.62），但焦煤回落部分对冲（弹性 0.18）。综合成本上行约 2.4%，需求侧无明显变化下，价格中位数路径升至 4380（+1.6%）。
            </p>
            <p>
              <strong className="text-text-primary">风险点</strong>：若终端需求边际转弱（极端情景概率 5%），价格可能跌破 4080，触发 cost_support_pressure 信号升级。
            </p>
            <p>
              <strong className="text-text-primary">建议行动</strong>：当前 RB 多仓可继续持有；若铁矿持续上涨且终端需求未跟进，考虑减仓 50% 至盈亏平衡线 4280 上方。
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

function ScenarioSlider({ label, min, max, default_ }: { label: string; min: number; max: number; default_: number }) {
  const [value, setValue] = useState(default_);
  return (
    <div>
      <div className="flex items-center justify-between text-caption mb-1">
        <span className="text-text-muted">{label}</span>
        <span className={cn("font-mono tabular-nums", value >= 0 ? "text-data-up" : "text-data-down")}>
          {value >= 0 ? "+" : ""}{value}{label.includes("天") || label.includes("次") ? "" : "%"}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => setValue(Number(e.target.value))}
        className="w-full h-1 bg-bg-surface-raised rounded-full appearance-none cursor-pointer accent-brand-emerald"
      />
    </div>
  );
}

function ScenarioStat({ label, value, desc, colorClass }: { label: string; value: string; desc: string; colorClass: string }) {
  return (
    <div className="bg-bg-base rounded-sm p-3">
      <div className="text-caption text-text-muted">{label}</div>
      <div className={cn("text-h2 font-mono tabular-nums mt-1", colorClass)}>{value}</div>
      <div className="text-caption text-text-muted mt-1">{desc}</div>
    </div>
  );
}

function ProbabilityFan() {
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
          <linearGradient id="fanGrad50" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.3" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        {[80, 160, 240].map((y) => (
          <line key={y} x1="0" y1={y} x2="800" y2={y} stroke="#1A1A1A" strokeWidth="0.5" />
        ))}
        {/* Vertical separator: history vs prediction */}
        <line x1="320" y1="0" x2="320" y2="320" stroke="#404040" strokeWidth="1" strokeDasharray="3 2" />
        <text x="324" y="16" className="text-[11px] fill-text-muted">预测开始 →</text>
        {/* Historical line */}
        <path
          d="M 0 220 L 40 215 L 80 218 L 120 200 L 160 195 L 200 180 L 240 175 L 280 168 L 320 160"
          fill="none"
          stroke="#A3A3A3"
          strokeWidth="1.5"
        />
        {/* P5-P95 fan (widest) */}
        <path
          d="M 320 160 L 800 30 L 800 290 L 320 160 Z"
          fill="url(#fanGrad95)"
        />
        {/* P25-P75 fan */}
        <path
          d="M 320 160 L 800 90 L 800 230 L 320 160 Z"
          fill="url(#fanGrad75)"
        />
        {/* P50 line */}
        <path
          d="M 320 160 L 800 130"
          fill="none"
          stroke="#10B981"
          strokeWidth="2"
          strokeDasharray="0"
        />
        {/* Current price marker */}
        <circle cx="320" cy="160" r="5" fill="#F97316" />
        <circle cx="320" cy="160" r="10" fill="#F97316" fillOpacity="0.3" />
        {/* Annotations */}
        <text x="780" y="35" textAnchor="end" className="text-[10px] fill-data-up font-mono">5% &gt; 4720</text>
        <text x="780" y="135" textAnchor="end" className="text-[10px] fill-text-primary font-mono">P50 4380</text>
        <text x="780" y="295" textAnchor="end" className="text-[10px] fill-data-down font-mono">5% &lt; 4080</text>
      </svg>
    </div>
  );
}
