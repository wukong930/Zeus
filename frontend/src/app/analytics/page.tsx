"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { MetricTile } from "@/components/MetricTile";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { DistributionBars } from "@/components/charts/DistributionBars";
import { DriftSparkline } from "@/components/charts/DriftSparkline";
import { ReliabilityCurve } from "@/components/charts/ReliabilityCurve";
import {
  fetchAttributionReport,
  fetchDriftSnapshot,
  fetchLearningHypotheses,
  fetchThresholdCalibrationReport,
  type AttributionReport,
  type AttributionSlice,
  type DriftMetric,
  type DriftSnapshot,
  type LearningHypothesis,
  type ThresholdCalibrationReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export default function AnalyticsPage() {
  const [tab, setTab] = useState<"attribution" | "calibration" | "hypotheses" | "drift">("attribution");
  const { text } = useI18n();

  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">{text("Analytics")}</h1>
        <p className="text-sm text-text-secondary mt-1">{text("系统运行健康度 + 个人交易归因")}</p>
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
            {text(t.label)}
            {t.desc && <span className="ml-2 text-caption text-brand-orange">{text(t.desc)}</span>}
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
  const [source, setSource] = useState<DataSourceState>("loading");
  const { text } = useI18n();

  useEffect(() => {
    let mounted = true;
    fetchAttributionReport()
      .then((data) => {
        if (!mounted) return;
        setReport(data);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setReport(null);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (!report) {
    return (
      <div className="space-y-5 animate-fade-in">
        <div className="flex justify-end">
          <DataSourceBadge state={source} />
        </div>
        <Card variant="flat" className="py-12 text-center">
          <div className="text-sm text-text-secondary">
            {text(source === "loading" ? "归因报告加载中" : "归因报告暂不可用")}
          </div>
        </Card>
      </div>
    );
  }

  const signalSlices = toSliceData(report.slices.signal_type);
  const categorySlices = toSliceData(report.slices.category);
  const p80Mae = report.risk_assessment.stop_loss?.p80_mae ?? null;
  const p80Mfe = report.risk_assessment.take_profit?.p80_mfe ?? null;
  const closedRate =
    report.total_recommendations > 0
      ? report.closed_recommendations / report.total_recommendations
      : 0;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex justify-end">
        <DataSourceBadge state={source} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-5">
        <Stat label="本月推荐数" value={String(report.total_recommendations)} trend="live" />
        <Stat label="已归因笔数" value={String(report.closed_recommendations)} trend="closed" />
        <Stat label="本月胜率" value={`${(report.win_rate * 100).toFixed(1)}%`} trend="runtime" />
        <Stat label="期望 PnL" value={formatPnl(report.expected_pnl)} trend="attributed" />
        <Stat
          label="闭环率"
          value={`${(closedRate * 100).toFixed(1)}%`}
          trend={`${report.closed_recommendations}/${report.total_recommendations}`}
        />
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>胜率切片分析</CardTitle>
            <CardSubtitle>按维度看哪些场景下系统表现最好</CardSubtitle>
          </div>
        </CardHeader>
        {signalSlices.length || categorySlices.length ? (
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
        ) : (
          <div className="py-8 text-center text-sm text-text-secondary">
            {text("暂无足够样本生成切片")}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <ChartFrame
          title="Stop Loss 评估"
          subtitle="MAE 分布看止损是太紧还是太松"
          metric={p80Mae === null ? "P80 --" : `P80 ${p80Mae.toFixed(2)}`}
        >
          {p80Mae === null ? <EmptyChartState label="暂无 MAE 样本" /> : <MAEDistribution />}
          <div className="text-sm text-text-secondary leading-relaxed mt-3">
            <strong className="text-text-primary">P80 MAE</strong>：
            {p80Mae === null ? "--" : p80Mae.toFixed(2)}。归因只出报表，不自动改止损。
          </div>
        </ChartFrame>

        <ChartFrame
          title="Take Profit 评估"
          subtitle="MFE 分布看止盈是否过早"
          metric={p80Mfe === null ? "P80 --" : `P80 ${p80Mfe.toFixed(2)}`}
        >
          {p80Mfe === null ? <EmptyChartState label="暂无 MFE 样本" /> : <MFEDistribution />}
          <div className="text-sm text-text-secondary leading-relaxed mt-3">
            <strong className="text-text-primary">P80 MFE</strong>：
            {p80Mfe === null ? "--" : p80Mfe.toFixed(2)}。止盈参数仍需人工评审。
          </div>
        </ChartFrame>
      </div>
    </div>
  );
}

function toSliceData(
  slices: AttributionSlice[] | undefined
) {
  if (!slices || slices.length === 0) return [];
  return slices.map((slice) => ({
    label: slice.label,
    winRate: slice.win_rate,
    samples: slice.samples,
    expReturn: slice.expected_pnl,
  }));
}

function EmptyChartState({ label }: { label: string }) {
  const { text } = useI18n();
  return (
    <div className="flex h-32 items-center justify-center rounded-sm border border-border-subtle bg-bg-base text-sm text-text-secondary">
      {text(label)}
    </div>
  );
}

function formatPnl(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function CalibrationTab() {
  const [report, setReport] = useState<ThresholdCalibrationReport | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const { text } = useI18n();

  useEffect(() => {
    let mounted = true;
    fetchThresholdCalibrationReport()
      .then((data) => {
        if (!mounted) return;
        setReport(data);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setReport(null);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (!report) {
    return (
      <div className="space-y-5 animate-fade-in">
        <div className="flex justify-end">
          <DataSourceBadge state={source} />
        </div>
        <Card variant="flat" className="py-12 text-center">
          <div className="text-sm text-text-secondary">
            {text(source === "loading" ? "校准报告加载中" : "校准报告暂不可用")}
          </div>
        </Card>
      </div>
    );
  }

  const auto = report.suggested_thresholds.auto;
  const notify = report.suggested_thresholds.notify;
  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex justify-end">
        <DataSourceBadge state={source} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <Stat label="校准样本" value={String(report.samples)} trend="resolved" />
        <Stat
          label="命中率"
          value={`${report.samples > 0 ? ((report.hits / report.samples) * 100).toFixed(1) : "0.0"}%`}
          trend={`${report.hits}/${report.samples}`}
        />
        <Stat
          label="建议 auto"
          value={auto.toFixed(2)}
          trend={`current ${report.current_thresholds.auto.toFixed(2)}`}
          trendNegative={report.review_required}
        />
        <Stat
          label="建议 notify"
          value={notify.toFixed(2)}
          trend={`current ${report.current_thresholds.notify.toFixed(2)}`}
          trendNegative={report.review_required}
        />
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>校准仪表盘</CardTitle>
            <CardSubtitle>按置信度分箱展示真实样本、命中率和校准偏差</CardSubtitle>
          </div>
        </CardHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-caption text-text-muted border-b border-border-subtle">
              <th className="text-left py-2 px-3 font-medium">置信度分箱</th>
              <th className="text-right py-2 px-3 font-medium">样本量</th>
              <th className="text-right py-2 px-3 font-medium">平均置信度</th>
              <th className="text-right py-2 px-3 font-medium">命中率</th>
              <th className="text-right py-2 px-3 font-medium">校准偏差</th>
              <th className="text-left py-2 px-3 font-medium">状态</th>
              <th className="text-left py-2 px-3 font-medium">样本占比</th>
            </tr>
          </thead>
          <tbody>
            {report.bins.map((bin) => (
              <tr key={`${bin.lower}-${bin.upper}`} className="border-b border-border-subtle hover:bg-bg-surface-raised">
                <td className="py-3 px-3 font-mono">
                  {bin.lower.toFixed(1)} - {bin.upper.toFixed(1)}
                </td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">
                  <span className={cn(bin.samples === 0 && "text-text-muted")}>{bin.samples}</span>
                  <span className="text-text-muted"> / {report.samples}</span>
                </td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">{formatNullableNumber(bin.avg_confidence)}</td>
                <td className="py-3 px-3 text-right font-mono tabular-nums">{formatNullablePercent(bin.hit_rate)}</td>
                <td className={cn("py-3 px-3 text-right font-mono tabular-nums", calibrationGapClass(bin.calibration_gap))}>
                  {formatSignedNullableNumber(bin.calibration_gap)}
                </td>
                <td className="py-3 px-3">
                  <CalibrationBinBadge samples={bin.samples} gap={bin.calibration_gap} />
                </td>
                <td className="py-3 px-3">
                  <div className="w-32 h-1.5 bg-bg-surface-raised rounded-full relative">
                    <div
                      className="absolute top-0 left-0 h-full bg-brand-emerald rounded-full"
                      style={{
                        width: `${report.samples > 0 ? Math.min(100, (bin.samples / report.samples) * 100) : 0}%`,
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <ChartFrame
        title="Reliability Diagram"
        subtitle={`ECE ${formatNullablePercent(report.expected_calibration_error)} -> ${formatNullablePercent(report.projected_calibration_error)} · Δ ${formatNullablePercent(report.calibration_error_improvement)}`}
        action={report.review_required ? <Badge variant="orange">review required</Badge> : <Badge variant="emerald">stable</Badge>}
      >
        <ReliabilityDiagram report={report} />
      </ChartFrame>
    </div>
  );
}

function CalibrationBinBadge({ samples, gap }: { samples: number; gap: number | null }) {
  if (samples === 0 || gap === null) return <Badge variant="neutral">no samples</Badge>;
  if (Math.abs(gap) >= 0.2) return <Badge variant="orange">review</Badge>;
  return <Badge variant="emerald">stable</Badge>;
}

function DriftTab() {
  const [snapshot, setSnapshot] = useState<DriftSnapshot | null>(null);
  const [source, setSource] = useState<DataSourceState>("loading");
  const { text } = useI18n();

  useEffect(() => {
    let mounted = true;
    fetchDriftSnapshot()
      .then((data) => {
        if (!mounted) return;
        setSnapshot(data);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setSnapshot(null);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (!snapshot) {
    return (
      <div className="space-y-5 animate-fade-in">
        <div className="flex justify-end">
          <DataSourceBadge state={source} />
        </div>
        <Card variant="flat" className="py-12 text-center">
          <div className="text-sm text-text-secondary">
            {text(source === "loading" ? "Drift 指标加载中" : "Drift 指标暂不可用")}
          </div>
        </Card>
      </div>
    );
  }

  const metrics = snapshot.metrics;
  const featureMetrics = metrics.filter((metric) => metric.metric_type === "feature_distribution");
  const trendValues = metrics
    .filter((metric) => metric.psi !== null)
    .slice()
    .reverse()
    .map((metric) => metric.psi as number)
    .slice(-14);
  const latestAt = snapshot.latest_at ? new Date(snapshot.latest_at).toLocaleString() : text("暂无记录");
  const statusMeta = driftStatusMeta(snapshot.status);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex justify-end">
        <DataSourceBadge state={source} />
      </div>
      <Card variant="flat" className={cn("border-l-[3px]", statusMeta.borderClass)}>
        <div className="flex items-center gap-3">
          <div className={cn("w-2 h-2 rounded-full animate-heartbeat", statusMeta.dotClass)} />
          <div>
            <div className="text-h3 text-text-primary">
              {text("Drift 状态")}：{text(statusMeta.label)}
            </div>
            <p className="text-sm text-text-secondary mt-1">
              {metrics.length > 0
                ? `${text("最近一次计算")} ${latestAt} · ${metrics.length} ${text("条漂移指标")} · red ${snapshot.severity_counts.red ?? 0} / yellow ${snapshot.severity_counts.yellow ?? 0}`
                : text("调度器尚未写入 Drift 指标。")}
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
            {(featureMetrics.length ? featureMetrics : metrics).slice(0, 8).map((metric) => (
              <div key={metric.id} className="flex items-center gap-3">
                <div className="w-28 truncate text-sm text-text-secondary" title={metricLabel(metric)}>
                  {metricLabel(metric)}
                </div>
                <div className="flex-1 h-2 bg-bg-surface-raised rounded-full">
                  <div
                    className={cn("h-full rounded-full", driftSeverityBar(metric.drift_severity))}
                    style={{ width: `${Math.min(100, ((metric.psi ?? 0) / 0.5) * 100)}%` }}
                  />
                </div>
                <div className="w-12 text-right font-mono text-sm tabular-nums">{formatNullableNumber(metric.psi)}</div>
              </div>
            ))}
            {metrics.length === 0 && (
              <div className="py-8 text-center text-sm text-text-secondary">
                {text("暂无 Drift 指标")}
              </div>
            )}
          </div>
        </Card>

        <ChartFrame title="历史 Drift 趋势" subtitle="PSI rolling 14d · warning line 0.25">
          {trendValues.length >= 2 ? (
            <DriftSparkline values={trendValues} />
          ) : (
            <EmptyChartState label="暂无足够样本生成 Drift 趋势" />
          )}
        </ChartFrame>
      </div>
    </div>
  );
}

function driftStatusMeta(status: string) {
  if (status === "red") {
    return {
      label: "严重漂移",
      borderClass: "border-l-data-down",
      dotClass: "bg-data-down shadow-glow-red",
    };
  }
  if (status === "yellow") {
    return {
      label: "需要关注",
      borderClass: "border-l-brand-orange",
      dotClass: "bg-brand-orange shadow-glow-orange",
    };
  }
  if (status === "green") {
    return {
      label: "正常",
      borderClass: "border-l-brand-emerald",
      dotClass: "bg-brand-emerald-bright shadow-glow-emerald",
    };
  }
  return {
    label: "暂无数据",
    borderClass: "border-l-border-default",
    dotClass: "bg-text-muted",
  };
}

function metricLabel(metric: DriftMetric): string {
  return metric.feature_name || metric.category || metric.metric_type;
}

function driftSeverityBar(severity: string): string {
  if (severity === "red") return "bg-data-down";
  if (severity === "yellow") return "bg-brand-orange";
  return "bg-brand-emerald";
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

  const hypothesisStats = useMemo(() => {
    let proposed = 0;
    let shadowTesting = 0;
    let weakEvidence = 0;
    for (const row of rows) {
      if (row.status === "proposed") proposed += 1;
      if (row.status === "shadow_testing") shadowTesting += 1;
      if (row.evidence_strength === "weak_evidence") weakEvidence += 1;
    }
    return {
      proposed,
      shadowTesting,
      total: rows.length,
      weakEvidence,
    };
  }, [rows]);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <Stat label="假设总数" value={String(hypothesisStats.total)} trend="monthly" />
        <Stat label="待评审" value={String(hypothesisStats.proposed)} trend="queue" />
        <Stat label="Shadow 中" value={String(hypothesisStats.shadowTesting)} trend="30d" />
        <Stat label="弱证据" value={String(hypothesisStats.weakEvidence)} trend="flagged" />
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
  const { text } = useI18n();

  return (
    <div>
      <div className="text-caption text-text-muted uppercase mb-2">{text(title)}</div>
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
    <MetricTile
      label={label}
      value={value}
      trend={trend}
      tone={trendNegative ? "down" : "up"}
    />
  );
}

function SliceTable({
  title,
  data,
}: {
  title: string;
  data: { label: string; winRate: number; samples: number; expReturn: number }[];
}) {
  const { text } = useI18n();

  return (
    <div>
      <div className="text-caption text-text-muted uppercase mb-3">{text(title)}</div>
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
  return <DistributionBars buckets={buckets} tone="down" markerIndex={4} />;
}

function MFEDistribution() {
  const buckets = [3, 8, 15, 22, 28, 24, 18, 12, 8, 4];
  return <DistributionBars buckets={buckets} tone="up" markerIndex={5} />;
}

function ReliabilityDiagram({ report }: { report: ThresholdCalibrationReport | null }) {
  const points =
    report?.bins
      .filter((bin) => bin.samples > 0 && bin.avg_confidence !== null && bin.hit_rate !== null)
      .map((bin) => ({ x: bin.avg_confidence as number, y: bin.hit_rate as number })) ?? [];
  if (points.length < 2) {
    return <EmptyChartState label="暂无足够样本生成可靠性曲线" />;
  }
  const label = report && report.samples > 0 ? `${report.samples} resolved signals` : "waiting for resolved signals";
  return <ReliabilityCurve points={points} label={label} />;
}

function formatNullablePercent(value: number | null | undefined) {
  return value == null ? "-" : `${(value * 100).toFixed(1)}%`;
}

function formatNullableNumber(value: number | null | undefined) {
  return value == null ? "-" : value.toFixed(3);
}

function formatSignedNullableNumber(value: number | null | undefined) {
  if (value == null) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}`;
}

function calibrationGapClass(value: number | null | undefined) {
  if (value == null) return "text-text-muted";
  if (Math.abs(value) >= 0.2) return "text-severity-high-fg";
  return "text-text-secondary";
}
