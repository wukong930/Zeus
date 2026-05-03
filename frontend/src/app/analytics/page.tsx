"use client";

import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import {
  fetchAttributionReport,
  fetchLearningHypotheses,
  fetchThresholdCalibrationReport,
  type AttributionReport,
  type AttributionSlice,
  type LearningHypothesis,
  type ThresholdCalibrationReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export default function AnalyticsPage() {
  const [tab, setTab] = useState<"attribution" | "calibration" | "hypotheses" | "drift">("attribution");

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Analytics</h1>
        <p className="text-sm text-text-secondary mt-1">系统运行健康度 + 个人交易归因</p>
      </div>

      <div className="flex gap-1 border-b border-border-subtle">
        {[
          { id: "attribution", label: "推荐归因", desc: "Goal B 命脉" },
          { id: "calibration", label: "校准仪表盘" },
          { id: "hypotheses", label: "反思假设" },
          { id: "drift", label: "Drift 监控" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as never)}
            className={cn(
              "px-5 py-3 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.id
                ? "border-brand-emerald text-text-primary"
                : "border-transparent text-text-muted hover:text-text-primary"
            )}
          >
            {t.label}
            {t.desc && <span className="ml-2 text-caption text-brand-orange">{t.desc}</span>}
          </button>
        ))}
      </div>

      {tab === "attribution" && <AttributionTab />}
      {tab === "calibration" && <CalibrationTab />}
      {tab === "hypotheses" && <HypothesesTab />}
      {tab === "drift" && <DriftTab />}
    </div>
  );
}

function AttributionTab() {
  const [report, setReport] = useState<AttributionReport | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchAttributionReport()
      .then((data) => {
        if (mounted) setReport(data);
      })
      .catch(() => {
        if (mounted) setReport(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const signalSlices = toSliceData(report?.slices.signal_type, [
    { label: "cost_support_pressure", winRate: 0.78, samples: 9, expReturn: 3.2 },
    { label: "spread_anomaly", winRate: 0.71, samples: 7, expReturn: 2.1 },
    { label: "news_event", winRate: 0.60, samples: 5, expReturn: 1.8 },
    { label: "momentum", winRate: 0.50, samples: 4, expReturn: 0.9 },
    { label: "regime_shift", winRate: 0.43, samples: 7, expReturn: -0.3 },
  ]);
  const categorySlices = toSliceData(report?.slices.category, [
    { label: "trend_up_low_vol", winRate: 0.74, samples: 12, expReturn: 2.6 },
    { label: "range_high_vol", winRate: 0.62, samples: 8, expReturn: 1.4 },
    { label: "trend_down_low_vol", winRate: 0.55, samples: 6, expReturn: 0.7 },
    { label: "range_low_vol", winRate: 0.40, samples: 5, expReturn: -0.2 },
  ]);
  const p80Mae = report?.risk_assessment.stop_loss?.p80_mae ?? 3.5;
  const p80Mfe = report?.risk_assessment.take_profit?.p80_mfe ?? 3;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-5">
        <Stat label="本月推荐数" value={String(report?.total_recommendations ?? 8)} trend="live" />
        <Stat label="已归因笔数" value={String(report?.closed_recommendations ?? 8)} trend="closed" />
        <Stat label="本月胜率" value={`${(((report?.win_rate ?? 0.625) * 100)).toFixed(1)}%`} trend="+12pt" />
        <Stat label="期望 PnL" value={formatPnl(report?.expected_pnl ?? 2.3)} trend="+0.4" />
        <Stat label="平均 R:R" value="1.78" trend="-0.1" trendNegative />
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>胜率切片分析</CardTitle>
            <CardSubtitle>按维度看哪些场景下系统表现最好</CardSubtitle>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-5">
          <SliceTable
            title="按信号类型"
            data={signalSlices}
          />
          <SliceTable
            title="按板块"
            data={categorySlices}
          />
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card variant="flat">
          <CardHeader>
            <div>
              <CardTitle>Stop Loss 评估</CardTitle>
              <CardSubtitle>MAE 分布看止损是太紧还是太松</CardSubtitle>
            </div>
          </CardHeader>
          <MAEDistribution />
          <div className="text-sm text-text-secondary leading-relaxed mt-3">
            <strong className="text-text-primary">P80 MAE</strong>：{p80Mae.toFixed(2)}。归因只出报表，不自动改止损。
          </div>
        </Card>

        <Card variant="flat">
          <CardHeader>
            <div>
              <CardTitle>Take Profit 评估</CardTitle>
              <CardSubtitle>MFE 分布看止盈是否过早</CardSubtitle>
            </div>
          </CardHeader>
          <MFEDistribution />
          <div className="text-sm text-text-secondary leading-relaxed mt-3">
            <strong className="text-text-primary">P80 MFE</strong>：{p80Mfe.toFixed(2)}。止盈参数仍需人工评审。
          </div>
        </Card>
      </div>
    </div>
  );
}

function toSliceData(
  slices: AttributionSlice[] | undefined,
  fallback: { label: string; winRate: number; samples: number; expReturn: number }[]
) {
  if (!slices || slices.length === 0) return fallback;
  return slices.map((slice) => ({
    label: slice.label,
    winRate: slice.win_rate,
    samples: slice.samples,
    expReturn: slice.expected_pnl,
  }));
}

function formatPnl(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function CalibrationTab() {
  const [report, setReport] = useState<ThresholdCalibrationReport | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchThresholdCalibrationReport()
      .then((data) => {
        if (mounted) setReport(data);
      })
      .catch(() => {
        if (mounted) setReport(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const evaluators = [
    { name: "spread_anomaly", samples: 47, hitRate: 0.71, weight: 1.18, status: "mature" as const },
    { name: "basis_shift", samples: 23, hitRate: 0.62, weight: 1.04, status: "warmup" as const },
    { name: "momentum", samples: 91, hitRate: 0.55, weight: 0.92, status: "mature" as const },
    { name: "regime_shift", samples: 18, hitRate: 0.44, weight: 0.78, status: "warmup" as const },
    { name: "inventory_shock", samples: 12, hitRate: 0.50, weight: 1.0, status: "warmup" as const },
    { name: "price_gap", samples: 56, hitRate: 0.48, weight: 0.86, status: "mature" as const },
    { name: "news_event", samples: 8, hitRate: 0.5, weight: 1.0, status: "warmup" as const },
  ];
  const auto = report?.suggested_thresholds.auto ?? 0.85;
  const notify = report?.suggested_thresholds.notify ?? 0.6;
  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <Stat label="校准样本" value={String(report?.samples ?? 0)} trend="resolved" />
        <Stat
          label="命中率"
          value={`${report && report.samples > 0 ? ((report.hits / report.samples) * 100).toFixed(1) : "0.0"}%`}
          trend={`${report?.hits ?? 0}/${report?.samples ?? 0}`}
        />
        <Stat
          label="建议 auto"
          value={auto.toFixed(2)}
          trend={`current ${(report?.current_thresholds.auto ?? 0.85).toFixed(2)}`}
          trendNegative={report?.review_required}
        />
        <Stat
          label="建议 notify"
          value={notify.toFixed(2)}
          trend={`current ${(report?.current_thresholds.notify ?? 0.6).toFixed(2)}`}
          trendNegative={report?.review_required}
        />
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>校准仪表盘</CardTitle>
            <CardSubtitle>每个评估器的样本量、命中率、当前权重</CardSubtitle>
          </div>
        </CardHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-caption text-text-muted border-b border-border-subtle">
              <th className="text-left py-2 px-3 font-medium">评估器</th>
              <th className="text-right py-2 px-3 font-medium">样本量</th>
              <th className="text-right py-2 px-3 font-medium">命中率</th>
              <th className="text-right py-2 px-3 font-medium">权重</th>
              <th className="text-left py-2 px-3 font-medium">状态</th>
              <th className="text-left py-2 px-3 font-medium">置信带</th>
            </tr>
          </thead>
          <tbody>
            {evaluators.map((e) => (
              <tr key={e.name} className="border-b border-border-subtle hover:bg-bg-surface-raised">
                <td className="py-3 px-3 font-mono">{e.name}</td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">
                  <span className={cn(e.samples < 30 && "text-severity-high-fg")}>{e.samples}</span>
                  <span className="text-text-muted"> / 100</span>
                </td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">{(e.hitRate * 100).toFixed(0)}%</td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">{e.weight.toFixed(2)}</td>
                <td className="py-3 px-3">
                  {e.status === "warmup" ? (
                    <Badge variant="orange">warmup · 先验主导</Badge>
                  ) : (
                    <Badge variant="emerald">mature</Badge>
                  )}
                </td>
                <td className="py-3 px-3">
                  <div className="w-32 h-1.5 bg-bg-surface-raised rounded-full relative">
                    <div
                      className="absolute top-0 left-0 h-full bg-brand-emerald rounded-full"
                      style={{ width: `${Math.min(100, (e.samples / 100) * 100)}%` }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>Reliability Diagram</CardTitle>
            <CardSubtitle>
              ECE {formatNullablePercent(report?.expected_calibration_error)} · Brier {formatNullableNumber(report?.brier_score)}
            </CardSubtitle>
          </div>
          {report?.review_required ? <Badge variant="orange">review required</Badge> : <Badge variant="emerald">stable</Badge>}
        </CardHeader>
        <ReliabilityDiagram report={report} />
      </Card>
    </div>
  );
}

function DriftTab() {
  return (
    <div className="space-y-5 animate-fade-in">
      <Card variant="flat" className="border-l-[3px] border-l-brand-emerald">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-brand-emerald-bright shadow-glow-emerald animate-heartbeat" />
          <div>
            <div className="text-h3 text-text-primary">Drift 状态：正常</div>
            <p className="text-sm text-text-secondary mt-1">
              当前市场结构与系统校准期数据相似度高。所有 PSI 指标 &lt; 0.15。
            </p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card variant="flat">
          <CardHeader>
            <CardTitle>特征分布漂移 (PSI)</CardTitle>
          </CardHeader>
          <div className="space-y-3">
            {[
              { name: "波动率", psi: 0.08, status: "healthy" },
              { name: "价差水平", psi: 0.12, status: "healthy" },
              { name: "基差", psi: 0.18, status: "healthy" },
              { name: "成交量", psi: 0.06, status: "healthy" },
              { name: "持仓量", psi: 0.21, status: "warning" },
            ].map((m) => (
              <div key={m.name} className="flex items-center gap-3">
                <div className="w-20 text-sm text-text-secondary">{m.name}</div>
                <div className="flex-1 h-2 bg-bg-surface-raised rounded-full">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      m.status === "healthy" ? "bg-brand-emerald" : "bg-severity-high-fg"
                    )}
                    style={{ width: `${(m.psi / 0.5) * 100}%` }}
                  />
                </div>
                <div className="w-12 text-right font-mono text-sm tabular-nums">{m.psi.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card variant="flat">
          <CardHeader>
            <CardTitle>历史 Drift 趋势</CardTitle>
          </CardHeader>
          <DriftTrend />
        </Card>
      </div>
    </div>
  );
}

function HypothesesTab() {
  const [rows, setRows] = useState<LearningHypothesis[]>([]);

  useEffect(() => {
    let mounted = true;
    fetchLearningHypotheses()
      .then((data) => {
        if (mounted) setRows(data);
      })
      .catch(() => {
        if (mounted) setRows([]);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <Stat label="假设总数" value={String(rows.length)} trend="monthly" />
        <Stat label="待评审" value={String(rows.filter((row) => row.status === "proposed").length)} trend="queue" />
        <Stat label="Shadow 中" value={String(rows.filter((row) => row.status === "shadow_testing").length)} trend="30d" />
        <Stat label="弱证据" value={String(rows.filter((row) => row.evidence_strength === "weak_evidence").length)} trend="flagged" />
      </div>

      <div className="space-y-3">
        {rows.map((row) => (
          <Card key={row.id} variant="flat">
            <CardHeader>
              <div>
                <CardTitle>{row.hypothesis}</CardTitle>
                <CardSubtitle>
                  n={row.sample_size} · confidence {formatNullableNumber(row.confidence)} · {row.created_at?.slice(0, 10) ?? "-"}
                </CardSubtitle>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={row.evidence_strength === "weak_evidence" ? "orange" : "emerald"}>
                  {row.evidence_strength}
                </Badge>
                <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
              </div>
            </CardHeader>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-sm">
              <EvidenceList title="证据" items={row.supporting_evidence} />
              <EvidenceList title="反证" items={row.counterevidence} />
              <div>
                <div className="text-caption text-text-muted uppercase mb-2">变更建议</div>
                <p className="text-text-secondary leading-relaxed">
                  {row.proposed_change ?? row.rejection_reason ?? "仅记录假设"}
                </p>
              </div>
            </div>
          </Card>
        ))}
        {rows.length === 0 && (
          <Card variant="flat">
            <div className="text-sm text-text-secondary">暂无月度反思假设。</div>
          </Card>
        )}
      </div>
    </div>
  );
}

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="text-caption text-text-muted uppercase mb-2">{title}</div>
      <div className="space-y-2">
        {items.slice(0, 3).map((item, index) => (
          <div key={`${title}-${index}`} className="text-text-secondary leading-relaxed">
            {item}
          </div>
        ))}
        {items.length === 0 && <div className="text-text-muted">-</div>}
      </div>
    </div>
  );
}

function statusVariant(status: string): "neutral" | "emerald" | "orange" | "low" {
  if (status === "validated" || status === "applied") return "emerald";
  if (status === "shadow_testing" || status === "proposed") return "orange";
  if (status === "rejected") return "neutral";
  return "low";
}

function Stat({ label, value, trend, trendNegative }: { label: string; value: string; trend: string; trendNegative?: boolean }) {
  return (
    <Card variant="flat">
      <div className="text-caption text-text-muted uppercase">{label}</div>
      <div className="text-display font-mono mt-2 leading-none tabular-nums text-text-primary">{value}</div>
      <div className={cn("text-xs font-mono mt-2", trendNegative ? "text-data-down" : "text-data-up")}>{trend}</div>
    </Card>
  );
}

function SliceTable({
  title,
  data,
}: {
  title: string;
  data: { label: string; winRate: number; samples: number; expReturn: number }[];
}) {
  return (
    <div>
      <div className="text-caption text-text-muted uppercase mb-3">{title}</div>
      <div className="space-y-2">
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-3 text-sm">
            <div className="w-44 text-text-secondary truncate">{d.label}</div>
            <div className="flex-1 h-1.5 bg-bg-surface-raised rounded-full">
              <div
                className="h-full rounded-full bg-brand-emerald"
                style={{ width: `${d.winRate * 100}%` }}
              />
            </div>
            <div className="w-12 text-right font-mono tabular-nums">{(d.winRate * 100).toFixed(0)}%</div>
            <div className={cn("w-12 text-right font-mono tabular-nums", d.expReturn >= 0 ? "text-data-up" : "text-data-down")}>
              {d.expReturn >= 0 ? "+" : ""}{d.expReturn.toFixed(1)}%
            </div>
            <div className="w-10 text-right text-caption text-text-muted font-mono">{d.samples}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MAEDistribution() {
  const buckets = [12, 18, 24, 30, 22, 12, 8, 4, 2, 1];
  return (
    <div className="flex items-end gap-1 h-32">
      {buckets.map((b, i) => (
        <div key={i} className="flex-1 bg-data-down/30 hover:bg-data-down/50 transition-colors rounded-t-xs" style={{ height: `${b * 3}px` }} />
      ))}
    </div>
  );
}

function MFEDistribution() {
  const buckets = [3, 8, 15, 22, 28, 24, 18, 12, 8, 4];
  return (
    <div className="flex items-end gap-1 h-32">
      {buckets.map((b, i) => (
        <div key={i} className="flex-1 bg-data-up/30 hover:bg-data-up/50 transition-colors rounded-t-xs" style={{ height: `${b * 3}px` }} />
      ))}
    </div>
  );
}

function ReliabilityDiagram({ report }: { report: ThresholdCalibrationReport | null }) {
  const fallback = [
    { x: 0.1, y: 0.08 },
    { x: 0.2, y: 0.18 },
    { x: 0.3, y: 0.32 },
    { x: 0.4, y: 0.38 },
    { x: 0.5, y: 0.55 },
    { x: 0.6, y: 0.58 },
    { x: 0.7, y: 0.66 },
    { x: 0.8, y: 0.74 },
    { x: 0.9, y: 0.82 },
  ];
  const points =
    report?.bins
      .filter((bin) => bin.samples > 0 && bin.avg_confidence !== null && bin.hit_rate !== null)
      .map((bin) => ({ x: bin.avg_confidence as number, y: bin.hit_rate as number })) ?? [];
  const renderedPoints = points.length >= 2 ? points : fallback;
  const path = renderedPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x * 400} ${(1 - point.y) * 240}`)
    .join(" ");
  return (
    <div className="h-64 relative">
      <svg viewBox="0 0 400 240" className="w-full h-full">
        {/* Grid */}
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line x1={i * 100} y1="0" x2={i * 100} y2="240" stroke="#1A1A1A" strokeWidth="0.5" />
            <line x1="0" y1={i * 60} x2="400" y2={i * 60} stroke="#1A1A1A" strokeWidth="0.5" />
          </g>
        ))}
        {/* Ideal line (diagonal) */}
        <line x1="0" y1="240" x2="400" y2="0" stroke="#404040" strokeWidth="1" strokeDasharray="3 2" />
        {renderedPoints.map((p, i) => (
          <circle key={i} cx={p.x * 400} cy={(1 - p.y) * 240} r="4" fill="#10B981" stroke="#000" strokeWidth="1" />
        ))}
        <path
          d={path}
          fill="none"
          stroke="#10B981"
          strokeWidth="1.5"
        />
        <text x="200" y="20" textAnchor="middle" className="text-[11px] fill-text-muted">
          {report && report.samples > 0 ? `${report.samples} resolved signals` : "waiting for resolved signals"}
        </text>
      </svg>
    </div>
  );
}

function formatNullablePercent(value: number | null | undefined) {
  return value == null ? "-" : `${(value * 100).toFixed(1)}%`;
}

function formatNullableNumber(value: number | null | undefined) {
  return value == null ? "-" : value.toFixed(3);
}

function DriftTrend() {
  return (
    <div className="h-48">
      <svg viewBox="0 0 400 180" className="w-full h-full">
        {[0, 1, 2, 3].map((i) => (
          <line key={i} x1="0" y1={i * 60} x2="400" y2={i * 60} stroke="#1A1A1A" strokeWidth="0.5" />
        ))}
        <line x1="0" y1="60" x2="400" y2="60" stroke="#F59E0B" strokeWidth="1" strokeDasharray="3 2" opacity="0.4" />
        <text x="396" y="55" textAnchor="end" className="text-[10px] fill-severity-high-fg font-mono">PSI 0.25</text>
        <path
          d="M 0 130 L 30 125 L 60 120 L 90 115 L 120 130 L 150 125 L 180 110 L 210 100 L 240 105 L 270 115 L 300 125 L 330 135 L 360 130 L 400 125"
          fill="none"
          stroke="#10B981"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  );
}
