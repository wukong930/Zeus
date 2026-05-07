"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Database,
  GitBranch,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sprout,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import {
  fetchCostChain,
  fetchCostHistories,
  fetchCostHistory,
  fetchCostQualityReport,
  simulateCostModel,
  type CostChain,
  type CostComponent,
  type CostInput,
  type CostModel,
  type CostQualityReport,
  type CostSnapshot,
} from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

type SectorKey = "ferrous" | "rubber";

const FERROUS_SYMBOL_ORDER = ["RB", "HC", "J", "JM", "I"] as const;
const RUBBER_SYMBOL_ORDER = ["RU", "NR"] as const;

const SECTOR_CONFIG: Record<
  SectorKey,
  {
    label: string;
    subtitle: string;
    defaultSymbol: string;
    symbols: readonly string[];
    chainLabel: string;
    quality: "ferrous" | "rubber";
  }
> = {
  ferrous: {
    label: "黑色系",
    subtitle: "黑色系成本链 · 分位成本曲线 · 调价模拟 · 信号触发面板",
    defaultSymbol: "RB",
    symbols: FERROUS_SYMBOL_ORDER,
    chainLabel: "JM → J → RB / HC",
    quality: "ferrous",
  },
  rubber: {
    label: "橡胶",
    subtitle: "NR → RU 成本链 · 产区季节性 · 加工费模拟 · 利润率信号",
    defaultSymbol: "RU",
    symbols: RUBBER_SYMBOL_ORDER,
    chainLabel: "NR → RU",
    quality: "rubber",
  },
};

const SYMBOL_META: Record<string, { label: string; role: string }> = {
  RB: { label: "螺纹钢", role: "成材利润锚" },
  HC: { label: "热卷", role: "热轧价差" },
  J: { label: "焦炭", role: "燃料成本" },
  JM: { label: "焦煤", role: "上游煤源" },
  I: { label: "铁矿石", role: "炉料成本" },
  RU: { label: "沪胶", role: "交割品成本" },
  NR: { label: "天然胶现货", role: "产区成本锚" },
};

type SourceState = Extract<DataSourceState, "loading" | "api" | "partial" | "fallback">;

interface SimulationInputs {
  ironOreIndex: number;
  cokeProcessing: number;
  conversionFee: number;
  thaiFieldLatex: number;
  seasonalFactorPct: number;
  ruProcessingFee: number;
  rawRubberRatio: number;
  currentPrice: number;
}

export default function IndustryLensPage() {
  const { text } = useI18n();
  const [sector, setSector] = useState<SectorKey>("ferrous");
  const config = SECTOR_CONFIG[sector];
  const [selected, setSelected] = useState<string>(SECTOR_CONFIG.ferrous.defaultSymbol);
  const [chain, setChain] = useState<CostChain | null>(null);
  const [histories, setHistories] = useState<Record<string, CostSnapshot[]>>({});
  const [qualityReport, setQualityReport] = useState<CostQualityReport | null>(null);
  const [source, setSource] = useState<SourceState>("loading");
  const [simInputs, setSimInputs] = useState<SimulationInputs>(() => emptySimulationInputs());
  const [simulated, setSimulated] = useState<CostModel | null>(null);

  useEffect(() => {
    let ignore = false;

    async function load() {
      const nextSelected = config.defaultSymbol;
      try {
        setSource("loading");
        setSelected(nextSelected);
        setChain(null);
        setHistories({});
        setQualityReport(null);
        const nextChain = await fetchCostChain(nextSelected);
        const [historyResults, qualityResult] = await Promise.all([
          fetchSectorCostHistories(config.symbols),
          fetchCostQualityReport(config.quality)
            .then((report) => ({ ok: true, report }) as const)
            .catch(() => ({ ok: false, report: null }) as const),
        ]);

        if (!ignore) {
          setChain(nextChain);
          setHistories(
            Object.fromEntries(historyResults.map((result) => [result.symbol, result.rows]))
          );
          setQualityReport(qualityResult.report);
          setSource(
            historyResults.every((result) => result.ok) && qualityResult.ok ? "api" : "partial"
          );
        }
      } catch {
        if (!ignore) {
          setSelected(nextSelected);
          setChain(null);
          setHistories({});
          setQualityReport(null);
          setSimulated(null);
          setSource("fallback");
        }
      }
    }

    load();
    return () => {
      ignore = true;
    };
  }, [config.defaultSymbol, config.quality, config.symbols]);

  const activeSymbol = config.symbols.includes(selected) ? selected : config.defaultSymbol;
  const selectedModel = chain?.results[activeSymbol] ?? chain?.results[config.defaultSymbol] ?? null;

  useEffect(() => {
    setSimInputs(selectedModel ? defaultSimulationInputs(selectedModel) : emptySimulationInputs());
    setSimulated(null);
  }, [activeSymbol, selectedModel]);

  useEffect(() => {
    if ((source !== "api" && source !== "partial") || !selectedModel) return;
    let ignore = false;
    const timer = window.setTimeout(() => {
      simulateCostModel(activeSymbol, {
        inputs_by_symbol: simulationInputsPayload(sector, simInputs),
        current_prices: { [activeSymbol]: simInputs.currentPrice },
      })
        .then((result) => {
          if (!ignore) setSimulated(result);
        })
        .catch(() => {
          if (!ignore) setSimulated(null);
        });
    }, 180);

    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [activeSymbol, sector, simInputs, source, selectedModel]);

  const displayModel = selectedModel ? simulated ?? selectedModel : null;
  const selectedHistory = histories[activeSymbol] ?? [];
  const signalRules = useMemo(
    () => (displayModel ? buildSignalRules(displayModel, selectedHistory) : []),
    [displayModel, selectedHistory]
  );
  const activeSignals = useMemo(
    () => signalRules.reduce((count, rule) => count + (rule.active ? 1 : 0), 0),
    [signalRules]
  );

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-h1 text-text-primary">{text("Industry Lens")}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {text(config.subtitle)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SectorToggle value={sector} onChange={setSector} />
          <DataSourceBadge state={source} />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => window.location.reload()}
            title={text("刷新成本模型")}
          >
            <RefreshCw className="w-4 h-4" />
            {text("刷新")}
          </Button>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {config.symbols.map((symbol) => (
          <CommodityButton
            key={symbol}
            symbol={symbol}
            model={chain?.results[symbol]}
            active={activeSymbol === symbol}
            onClick={() => setSelected(symbol)}
          />
        ))}
      </div>

      {!displayModel || !chain ? (
        <IndustryEmptyState source={source} sectorLabel={config.label} />
      ) : (
        <>
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <Card variant="flat" className="xl:col-span-7">
          <CardHeader>
            <div>
              <CardTitle>成本分解 — {symbolLabel(displayModel.symbol)}</CardTitle>
              <CardSubtitle>
                单位成本 {formatCurrency(displayModel.total_unit_cost)} / t · 模型{" "}
                {displayModel.formula_version}
              </CardSubtitle>
            </div>
            <Database className="w-4 h-4 text-brand-emerald-bright" />
          </CardHeader>
          <CostBreakdown components={displayModel.cost_breakdown} />
        </Card>

        <Card variant="flat" className="xl:col-span-5">
          <CardHeader>
            <div>
              <CardTitle>成本曲线分位数</CardTitle>
              <CardSubtitle>当前价格相对 P25/P50/P75/P90 的位置</CardSubtitle>
            </div>
            <Activity className="w-4 h-4 text-brand-orange" />
          </CardHeader>
          <CostQuantileChart model={displayModel} />
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
        <MetricCard
          label="当前价格"
          value={displayModel.current_price}
          fallback="N/A"
          suffix="/t"
          badge={profitBadge(displayModel)}
        />
        <MetricCard label="P50 中位成本" value={displayModel.breakevens.p50} suffix="/t" />
        <MetricCard label="P75 边际成本" value={displayModel.breakevens.p75} suffix="/t" />
        <MetricCard label="P90 边际成本" value={displayModel.breakevens.p90} suffix="/t" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <Card variant="flat" className="xl:col-span-5">
          <CardHeader>
            <div>
              <CardTitle>动态调价计算器</CardTitle>
              <CardSubtitle>滑动关键变量，实时调用模拟端点重算</CardSubtitle>
            </div>
            <SlidersHorizontal className="w-4 h-4 text-brand-emerald-bright" />
          </CardHeader>
          <SimulationControls
            sector={sector}
            model={displayModel}
            values={simInputs}
            onChange={setSimInputs}
            onReset={() => {
              setSimInputs(defaultSimulationInputs(displayModel));
              setSimulated(null);
            }}
          />
        </Card>

        <Card variant="flat" className="xl:col-span-4">
          <CardHeader>
            <div>
              <CardTitle>利润率趋势</CardTitle>
              <CardSubtitle>{selectedHistory.length} 个成本快照</CardSubtitle>
            </div>
          </CardHeader>
          <ProfitTrend history={selectedHistory} />
        </Card>

        <Card variant="flat" className="xl:col-span-3">
          <CardHeader>
            <div>
              <CardTitle>产业链全景</CardTitle>
              <CardSubtitle>{config.chainLabel}</CardSubtitle>
            </div>
            <GitBranch className="w-4 h-4 text-brand-orange" />
          </CardHeader>
          <ChainMap chain={chain} selected={activeSymbol} onSelect={setSelected} />
        </Card>
      </div>

      {sector === "rubber" ? <RubberSeasonalityPanel model={displayModel} values={simInputs} /> : null}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <Card variant="flat" className="xl:col-span-7">
          <CardHeader>
            <div>
              <CardTitle>成本信号触发条件</CardTitle>
              <CardSubtitle>{activeSignals} 个条件处于触发区间</CardSubtitle>
            </div>
            <Badge variant={activeSignals > 0 ? "orange" : "emerald"}>
              {activeSignals > 0 ? "ACTIVE" : "CLEAR"}
            </Badge>
          </CardHeader>
          <SignalRules rules={signalRules} />
        </Card>

        <Card variant="flat" className="xl:col-span-5">
          <CardHeader>
            <div>
              <CardTitle>数据来源透明度</CardTitle>
              <CardSubtitle>
                不确定度 ±{formatNumber(displayModel.uncertainty_pct * 100, { decimals: 1 })}%
              </CardSubtitle>
            </div>
          </CardHeader>
          <DataSources model={displayModel} />
        </Card>
      </div>

      {qualityReport ? (
        <QualityReportPanel report={qualityReport} />
      ) : (
        <QualityReportUnavailablePanel source={source} />
      )}
      {sector === "rubber" ? <RubberValidationPanel model={displayModel} /> : null}
        </>
      )}
    </div>
  );
}

async function fetchSectorCostHistories(symbols: readonly string[]) {
  try {
    const histories = await fetchCostHistories(symbols, 30);
    return symbols.map(
      (symbol) =>
        ({
          ok: true,
          symbol,
          rows: histories[symbol] ?? [],
        }) as const
    );
  } catch {
    return Promise.all(
      symbols.map(async (symbol) => {
        try {
          return { ok: true, symbol, rows: await fetchCostHistory(symbol, 30) } as const;
        } catch {
          return { ok: false, symbol, rows: [] as CostSnapshot[] } as const;
        }
      })
    );
  }
}

function IndustryEmptyState({
  source,
  sectorLabel,
}: {
  source: SourceState;
  sectorLabel: string;
}) {
  const { text } = useI18n();
  const loading = source === "loading";

  return (
    <Card variant="flat" className="py-14 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-sm border border-border-subtle bg-bg-base text-text-secondary">
        {loading ? <RefreshCw className="h-5 w-5 animate-spin" /> : <Database className="h-5 w-5" />}
      </div>
      <div className="mt-4 text-h3 text-text-primary">
        {text(loading ? "成本链加载中" : "成本链接口暂不可用")}
      </div>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-text-secondary">
        {text(loading
          ? "正在同步产业成本链、历史快照和质量评估。"
          : "当前不再展示模拟成本链，请等待后端成本模型恢复后再查看分位成本、信号触发和调价模拟。")}
      </p>
      <div className="mt-4 inline-flex items-center gap-2 rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-caption text-text-muted">
        <span>{text("当前板块")}</span>
        <span className="text-text-primary">{text(sectorLabel)}</span>
      </div>
    </Card>
  );
}

function CommodityButton({
  symbol,
  model,
  active,
  onClick,
}: {
  symbol: string;
  model?: CostModel;
  active: boolean;
  onClick: () => void;
}) {
  const margin = model?.profit_margin ?? null;
  return (
    <button
      onClick={onClick}
      className={cn(
        "min-w-[168px] rounded-sm border px-4 py-3 text-left transition-colors",
        active
          ? "bg-brand-emerald/15 border-brand-emerald text-text-primary"
          : "bg-bg-surface border-border-subtle text-text-secondary hover:bg-bg-surface-raised"
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm text-text-primary">{symbol}</span>
        <Badge variant={margin === null ? "neutral" : margin >= 0 ? "up" : "down"}>
          {margin === null ? "N/A" : `${formatNumber(margin * 100, { decimals: 1, signed: true })}%`}
        </Badge>
      </div>
      <div className="mt-1 text-sm font-medium">{symbolLabel(symbol)}</div>
      <div className="text-caption text-text-muted">{SYMBOL_META[symbol]?.role}</div>
    </button>
  );
}

function SectorToggle({
  value,
  onChange,
}: {
  value: SectorKey;
  onChange: (value: SectorKey) => void;
}) {
  return (
    <div className="flex h-9 rounded-sm border border-border-subtle bg-bg-surface p-0.5">
      {(Object.keys(SECTOR_CONFIG) as SectorKey[]).map((key) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={cn(
            "px-3 text-sm transition-colors rounded-xs",
            value === key
              ? "bg-brand-emerald/15 text-text-primary"
              : "text-text-secondary hover:text-text-primary"
          )}
        >
          {SECTOR_CONFIG[key].label}
        </button>
      ))}
    </div>
  );
}

function CostBreakdown({ components }: { components: CostComponent[] }) {
  const max = Math.max(...components.map((item) => Math.abs(item.value)), 1);
  const total = components.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="space-y-3">
      {components.map((item) => {
        const credit = item.value < 0;
        const width = Math.max(4, (Math.abs(item.value) / max) * 100);
        return (
          <div key={item.name} className="grid grid-cols-[minmax(104px,150px)_1fr_92px] gap-3 items-center">
            <div className="min-w-0 text-sm text-text-secondary truncate" title={item.name}>
              {componentLabel(item.name)}
            </div>
            <div className="h-7 bg-bg-base rounded-sm overflow-hidden relative">
              <div
                className={cn(
                  "h-full rounded-sm",
                  credit ? "bg-data-down/45" : "bg-brand-emerald/55"
                )}
                style={{ width: `${width}%` }}
              />
              <div className="absolute inset-0 flex items-center justify-end pr-2">
                <span className="text-caption font-mono tabular-nums text-text-secondary">
                  {formatNumber((Math.abs(item.value) / Math.max(Math.abs(total), 1)) * 100, {
                    decimals: 1,
                  })}
                  %
                </span>
              </div>
            </div>
            <div className="text-right font-mono text-sm tabular-nums text-text-primary">
              {formatCurrency(item.value)}
            </div>
          </div>
        );
      })}
      <div className="border-t border-border-default pt-3 mt-3 flex items-center gap-3">
        <div className="text-h3 text-text-primary">单位成本</div>
        <div className="flex-1" />
        <div className="text-h2 font-mono tabular-nums text-text-primary">
          {formatCurrency(total)}
        </div>
      </div>
    </div>
  );
}

function CostQuantileChart({ model }: { model: CostModel }) {
  const current = model.current_price ?? model.total_unit_cost;
  const quantiles = [
    { p: "P25", value: model.breakevens.p25, label: "低成本" },
    { p: "P50", value: model.breakevens.p50, label: "中位数" },
    { p: "P75", value: model.breakevens.p75, label: "高成本" },
    { p: "P90", value: model.breakevens.p90, label: "边际产能" },
  ];
  const values = [...quantiles.map((item) => item.value), current];
  const min = Math.min(...values) * 0.96;
  const max = Math.max(...values) * 1.04;
  const norm = (value: number) => clamp(((value - min) / Math.max(max - min, 1)) * 100, 0, 100);

  return (
    <div className="space-y-3 py-2">
      <div className="relative h-36 overflow-hidden rounded-sm border border-border-subtle bg-bg-base zeus-grid-surface">
        <svg viewBox="0 0 200 100" className="w-full h-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="costQuantileFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#10B981" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#10B981" stopOpacity="0.03" />
            </linearGradient>
          </defs>
          <path
            d="M 0 88 C 34 86 54 78 82 64 C 112 48 142 30 200 12 L 200 100 L 0 100 Z"
            fill="url(#costQuantileFill)"
          />
          <path
            d="M 0 88 C 34 86 54 78 82 64 C 112 48 142 30 200 12"
            fill="none"
            stroke="#10B981"
            strokeWidth="1.8"
            className="zeus-data-line"
          />
          <line
            x1={norm(current) * 2}
            y1="0"
            x2={norm(current) * 2}
            y2="100"
            stroke="#F97316"
            strokeWidth="1.5"
            strokeDasharray="3 2"
          />
        </svg>
        <div className="absolute top-2 -translate-x-1/2" style={{ left: `${norm(current)}%` }}>
          <Badge variant="orange">当前 {formatCurrency(current)}</Badge>
        </div>
      </div>

      <div className="space-y-2">
        {quantiles.map((item) => {
          const breached = current < item.value;
          return (
            <div key={item.p} className="grid grid-cols-[44px_1fr_86px_48px] gap-2 items-center text-sm">
              <div className="font-mono text-text-muted">{item.p}</div>
              <div className="h-2 bg-bg-surface-raised rounded-full relative">
                <div
                  className="absolute top-0 left-0 h-full bg-brand-emerald rounded-full"
                  style={{ width: `${norm(item.value)}%` }}
                />
                <div
                  className="absolute top-[-3px] w-0.5 h-4 bg-brand-orange"
                  style={{ left: `${norm(current)}%` }}
                />
              </div>
              <div className="text-right font-mono tabular-nums text-text-primary">
                {formatCurrency(item.value)}
              </div>
              <Badge variant={breached ? "critical" : "neutral"}>{breached ? "破位" : item.label}</Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  suffix,
  fallback = "--",
  badge,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  fallback?: string;
  badge?: { label: string; variant: "up" | "down" | "neutral" };
}) {
  return (
    <Card variant="flat">
      <div className="text-caption text-text-muted uppercase mb-2">{label}</div>
      <div className="text-display font-mono text-text-primary tabular-nums leading-none">
        {value === null ? fallback : formatCurrency(value)}
      </div>
      <div className="flex items-center gap-2 text-sm text-text-muted mt-3">
        {suffix ? <span>{suffix}</span> : null}
        {badge ? <Badge variant={badge.variant}>{badge.label}</Badge> : null}
      </div>
    </Card>
  );
}

function SimulationControls({
  sector,
  model,
  values,
  onChange,
  onReset,
}: {
  sector: SectorKey;
  model: CostModel;
  values: SimulationInputs;
  onChange: (value: SimulationInputs) => void;
  onReset: () => void;
}) {
  const priceBase = model.current_price ?? model.total_unit_cost;

  return (
    <div className="space-y-4">
      {sector === "ferrous" ? (
        <>
          <RangeControl
            label="铁矿石指数"
            value={values.ironOreIndex}
            min={500}
            max={1000}
            step={5}
            unit="CNY/t"
            onChange={(ironOreIndex) => onChange({ ...values, ironOreIndex })}
          />
          <RangeControl
            label="焦炭加工费"
            value={values.cokeProcessing}
            min={120}
            max={420}
            step={5}
            unit="CNY/t"
            onChange={(cokeProcessing) => onChange({ ...values, cokeProcessing })}
          />
          <RangeControl
            label="高炉加工费"
            value={values.conversionFee}
            min={520}
            max={980}
            step={5}
            unit="CNY/t"
            onChange={(conversionFee) => onChange({ ...values, conversionFee })}
          />
        </>
      ) : (
        <>
          <RangeControl
            label="泰国产区胶价"
            value={values.thaiFieldLatex}
            min={9000}
            max={15000}
            step={50}
            unit="CNY/t"
            onChange={(thaiFieldLatex) => onChange({ ...values, thaiFieldLatex })}
          />
          <RangeControl
            label="季节性因子"
            value={values.seasonalFactorPct * 100}
            min={-3}
            max={8}
            step={0.5}
            unit="%"
            onChange={(seasonalFactorPct) =>
              onChange({ ...values, seasonalFactorPct: seasonalFactorPct / 100 })
            }
          />
          <RangeControl
            label="RU 加工费"
            value={values.ruProcessingFee}
            min={700}
            max={1200}
            step={10}
            unit="CNY/t"
            onChange={(ruProcessingFee) => onChange({ ...values, ruProcessingFee })}
          />
          <RangeControl
            label="原胶折耗"
            value={values.rawRubberRatio}
            min={1}
            max={1.08}
            step={0.01}
            unit="t/t"
            onChange={(rawRubberRatio) => onChange({ ...values, rawRubberRatio })}
          />
        </>
      )}
      <RangeControl
        label="当前价格"
        value={values.currentPrice}
        min={Math.max(1, Math.round(priceBase * 0.75))}
        max={Math.max(2, Math.round(priceBase * 1.25))}
        step={10}
        unit="CNY/t"
        onChange={(currentPrice) => onChange({ ...values, currentPrice })}
      />
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={onReset} title="重置模拟参数">
          <RotateCcw className="w-4 h-4" />
          重置
        </Button>
      </div>
    </div>
  );
}

function RangeControl({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <div className="flex items-center gap-3 mb-2">
        <span className="text-sm text-text-secondary flex-1">{label}</span>
        <input
          value={Number.isFinite(value) ? value : 0}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-24 h-8 bg-bg-base border border-border-default rounded-sm px-2 text-right text-sm font-mono focus:border-brand-emerald focus:outline-none"
          type="number"
        />
        <span className="text-caption text-text-muted w-12">{unit}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : min}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-brand-emerald"
      />
    </label>
  );
}

function ProfitTrend({ history }: { history: CostSnapshot[] }) {
  const points = history.slice().reverse();
  const { text } = useI18n();

  if (points.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex h-36 items-center justify-center rounded-sm border border-dashed border-border-subtle bg-bg-base p-4 text-center text-sm text-text-secondary">
          {text("暂无真实历史成本快照")}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-secondary">{text("最新利润率")}</span>
          <Badge variant="neutral">--</Badge>
        </div>
      </div>
    );
  }

  const margins = points.map((row) => costSnapshotMargin(row) * 100);
  const min = Math.min(...margins, -1);
  const max = Math.max(...margins, 1);
  const x = (idx: number) => (idx / Math.max(points.length - 1, 1)) * 100;
  const y = (value: number) => 86 - ((value - min) / Math.max(max - min, 1)) * 72;
  const path = margins.map((value, idx) => `${idx === 0 ? "M" : "L"} ${x(idx)} ${y(value)}`).join(" ");
  const latest = margins[margins.length - 1] ?? 0;

  return (
    <div className="space-y-3">
      <div className="h-36 overflow-hidden rounded-sm border border-border-subtle bg-bg-base p-2 zeus-grid-surface">
        <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="profitTrendFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={latest >= 0 ? "#10B981" : "#EF4444"} stopOpacity="0.24" />
              <stop offset="100%" stopColor={latest >= 0 ? "#10B981" : "#EF4444"} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <line x1="0" y1={y(0)} x2="100" y2={y(0)} stroke="rgba(148,163,184,0.35)" strokeDasharray="3 2" />
          <path d={`${path} L 100 100 L 0 100 Z`} fill="url(#profitTrendFill)" />
          <path d={path} fill="none" stroke={latest >= 0 ? "#10B981" : "#EF4444"} strokeWidth="2" className="zeus-data-line" />
        </svg>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-secondary">{text("最新利润率")}</span>
        <Badge variant={latest >= 0 ? "up" : "down"}>
          {formatNumber(latest, { decimals: 2, signed: true })}%
        </Badge>
      </div>
    </div>
  );
}

function ChainMap({
  chain,
  selected,
  onSelect,
}: {
  chain: CostChain;
  selected: string;
  onSelect: (symbol: string) => void;
}) {
  return (
    <div className="space-y-2">
      {chain.symbols.map((symbol) => {
        const model = chain.results[symbol];
        return (
          <button
            key={symbol}
            onClick={() => onSelect(symbol)}
            className={cn(
              "w-full rounded-sm border p-3 text-left transition-colors",
              selected === symbol
                ? "border-brand-emerald bg-brand-emerald/10"
                : "border-border-subtle bg-bg-base hover:bg-bg-surface-raised"
            )}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-text-primary">{symbol}</span>
              <span className="text-sm text-text-secondary">{symbolLabel(symbol)}</span>
            </div>
            <div className="mt-1 text-caption text-text-muted">
              单位成本 {formatCurrency(model?.total_unit_cost ?? 0)}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function SignalRules({
  rules,
}: {
  rules: { condition: string; trigger: string; active: boolean; severity: "high" | "medium" | "low" }[];
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {rules.map((rule) => (
        <div
          key={`${rule.trigger}-${rule.condition}`}
          className={cn(
            "flex items-center gap-3 p-3 rounded-sm border min-h-[76px]",
            rule.active ? "bg-brand-orange/10 border-brand-orange" : "bg-bg-base border-border-subtle"
          )}
        >
          <div
            className={cn(
              "w-2.5 h-2.5 rounded-full shrink-0",
              rule.active ? "bg-brand-orange animate-heartbeat" : "bg-text-disabled"
            )}
          />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-text-primary">{rule.condition}</div>
            <div className="text-caption text-text-muted font-mono mt-1">{rule.trigger}</div>
          </div>
          <Badge variant={rule.active ? rule.severity : "neutral"}>
            {rule.active ? "触发" : "待机"}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function RubberSeasonalityPanel({
  model,
  values,
}: {
  model: CostModel;
  values: SimulationInputs;
}) {
  const active = rubberSeasonalityLabel(values.seasonalFactorPct);
  const sourceNames = Object.values(model.inputs)
    .filter((input) =>
      ["thai_field_latex_cny", "qingdao_bonded_spot_premium", "hainan_yunnan_collection_cost"].includes(
        input.name
      )
    )
    .map((input) => componentLabel(input.name));
  const originNames = sourceNames.length
    ? sourceNames
    : ["泰国产区胶价", "青岛保税区升水", "海南/云南收胶成本"];
  const { text } = useI18n();

  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>产区季节性</CardTitle>
          <CardSubtitle>
            {active.title} · 季节因子 {formatNumber(values.seasonalFactorPct * 100, { decimals: 1, signed: true })}%
          </CardSubtitle>
        </div>
        <Sprout className="w-4 h-4 text-brand-emerald-bright" />
      </CardHeader>

      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "停割期", months: "12-2月", value: "+6%" },
            { label: "低供给", months: "3-4月", value: "+4%" },
            { label: "开割初期", months: "5-6月", value: "+2%" },
            { label: "旺割期", months: "7-9月", value: "-1%" },
          ].map((item) => (
            <div
              key={item.label}
              className={cn(
                "rounded-sm border p-3 bg-bg-base",
                active.title === item.label ? "border-brand-emerald" : "border-border-subtle"
              )}
            >
              <div className="text-sm text-text-primary">{text(item.label)}</div>
              <div className="mt-1 text-caption text-text-muted">{item.months}</div>
              <div className="mt-3 font-mono text-h3 text-text-primary">{item.value}</div>
            </div>
          ))}
        </div>

        <div className="rounded-sm bg-bg-base border border-border-subtle p-4">
          <div className="text-caption text-text-muted uppercase mb-2">{text("Origin Basket")}</div>
          <div className="flex flex-wrap gap-2">
            {originNames.map((name) => (
              <Badge key={name} variant="neutral">
                {name}
              </Badge>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <QualityMetric
              label="产区胶价"
              value={formatCurrency(values.thaiFieldLatex)}
              suffix="泰国口径"
            />
            <QualityMetric
              label="RU 加工费"
              value={formatCurrency(values.ruProcessingFee)}
              suffix="交割品加工"
            />
          </div>
        </div>
      </div>
    </Card>
  );
}

function RubberValidationPanel({ model }: { model: CostModel }) {
  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>橡胶验证队列</CardTitle>
          <CardSubtitle>盈亏平衡价 · 产区冲击 · 生产级数据采集</CardSubtitle>
        </div>
        <ShieldCheck className="w-4 h-4 text-brand-emerald-bright" />
      </CardHeader>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[
          {
            title: "RU 盈亏平衡价",
            body: `当前 bootstrap P50 ${formatCurrency(model.breakevens.p50)}，P90 ${formatCurrency(
              model.breakevens.p90
            )}`,
            badge: "已接入",
          },
          {
            title: "产区供给冲击",
            body: "泰国干旱、强降雨、出口政策进入新闻事件联动队列",
            badge: "待接入",
          },
          {
            title: "生产级数据源",
            body: "青岛保税区、海南/云南、东南亚出口价、Drewry/CCFI",
            badge: "待采集",
          },
        ].map((item) => (
          <div key={item.title} className="rounded-sm bg-bg-base border border-border-subtle p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-h3 text-text-primary">{item.title}</div>
              <Badge variant={item.badge === "已接入" ? "emerald" : "orange"}>{item.badge}</Badge>
            </div>
            <p className="mt-3 text-sm text-text-secondary leading-relaxed">{item.body}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function QualityReportPanel({ report }: { report: CostQualityReport }) {
  const { text } = useI18n();
  const recommendation = recommendationLabel(report);
  const bestComparisons = report.benchmark_comparisons.slice(0, 4);
  const bestCases = report.signal_cases.slice(0, 3);

  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>数据质量评估</CardTitle>
          <CardSubtitle>
            公开基准误差 · 历史场景触发 · 付费数据源决策
          </CardSubtitle>
        </div>
        <ShieldCheck className="w-4 h-4 text-brand-emerald-bright" />
      </CardHeader>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <QualityMetric label="综合评分" value={`${report.data_quality_score}`} suffix="/100" />
        <QualityMetric
          label="平均误差"
          value={`${formatNumber(report.benchmark_error_avg_pct, { decimals: 2 })}%`}
          suffix="目标 < 5%"
        />
        <QualityMetric
          label="基准通过率"
          value={`${formatNumber(report.benchmark_pass_rate * 100, { decimals: 0 })}%`}
          suffix="公开参考"
        />
        <QualityMetric
          label="场景命中率"
          value={`${formatNumber(report.signal_case_hit_rate * 100, { decimals: 0 })}%`}
          suffix="历史压力"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_1fr_1fr] gap-5 mt-5">
        <div className="space-y-2">
          <div className="text-caption text-text-muted uppercase">{text("Benchmark Drift")}</div>
          {bestComparisons.map((item) => (
            <div
              key={`${item.symbol}-${item.metric}`}
              className="grid grid-cols-[58px_1fr_74px_64px] gap-2 items-center rounded-sm bg-bg-base border border-border-subtle p-2 text-sm"
            >
              <span className="font-mono text-text-primary">{item.symbol}</span>
              <span className="text-text-secondary truncate">{metricLabel(item.metric)}</span>
              <span className="font-mono text-right text-text-primary">
                {formatNumber(item.error_pct, { decimals: 2 })}%
              </span>
              <Badge variant={item.within_tolerance ? "emerald" : "orange"}>
                {item.within_tolerance ? "通过" : "偏离"}
              </Badge>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <div className="text-caption text-text-muted uppercase">{text("Historical Cases")}</div>
          {bestCases.map((item) => (
            <div
              key={item.case_id}
              className="rounded-sm bg-bg-base border border-border-subtle p-3"
            >
              <div className="flex items-center gap-2">
                <Badge variant={item.passed ? "emerald" : "orange"}>
                  {item.passed ? text("PASS") : text("REVIEW")}
                </Badge>
                <span className="text-sm text-text-primary truncate">{item.title}</span>
              </div>
              <div className="mt-2 text-caption text-text-muted font-mono truncate">
                {item.triggered_signals.join(" · ")}
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-sm bg-bg-base border border-border-subtle p-4">
          <div className="text-caption text-text-muted uppercase mb-2">{text("Purchase Decision")}</div>
          <div className="text-h3 text-text-primary">{recommendation.title}</div>
          <p className="text-sm text-text-secondary mt-2 leading-relaxed">
            {recommendation.body}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant={report.preferred_vendor ? "orange" : "emerald"}>
              {report.preferred_vendor ?? "暂不采购"}
            </Badge>
            <Badge variant="neutral">
              {new Date(report.generated_at).toISOString().slice(0, 10)}
            </Badge>
          </div>
        </div>
      </div>
    </Card>
  );
}

function QualityReportUnavailablePanel({ source }: { source: SourceState }) {
  const { text } = useI18n();
  const loading = source === "loading";

  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>{text("数据质量评估")}</CardTitle>
          <CardSubtitle>
            {text(loading ? "质量评估加载中" : "质量评估接口暂不可用")}
          </CardSubtitle>
        </div>
        {loading ? (
          <RefreshCw className="w-4 h-4 animate-spin text-text-muted" />
        ) : (
          <ShieldCheck className="w-4 h-4 text-text-muted" />
        )}
      </CardHeader>
      <div className="rounded-sm border border-dashed border-border-subtle bg-bg-base/60 px-4 py-8 text-center text-sm text-text-secondary">
        {text(loading
          ? "正在同步公开基准误差、历史场景触发和付费数据源决策。"
          : "成本链仍可查看，但本次没有质量评估结果；页面会明确显示质量评估不可用状态。")}
      </div>
    </Card>
  );
}

function QualityMetric({ label, value, suffix }: { label: string; value: string; suffix: string }) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm bg-bg-base border border-border-subtle p-3">
      <div className="text-caption text-text-muted uppercase">{text(label)}</div>
      <div className="mt-2 text-h2 font-mono text-text-primary tabular-nums">{value}</div>
      <div className="text-caption text-text-muted mt-1">{text(suffix)}</div>
    </div>
  );
}

function DataSources({ model }: { model: CostModel }) {
  const { text } = useI18n();
  const inputs = Object.values(model.inputs).slice(0, 8);
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {inputs.map((input) => (
          <SourceRow key={input.name} input={input} />
        ))}
      </div>
      <div className="border-t border-border-subtle pt-3">
        <div className="text-caption text-text-muted uppercase mb-2">{text("Sources")}</div>
        <div className="flex flex-wrap gap-2">
          {model.data_sources.map((source) => (
            <Badge key={source.name} variant="neutral">
              {source.name}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

function SourceRow({ input }: { input: CostInput }) {
  return (
    <div className="grid grid-cols-[1fr_88px_58px] gap-2 items-center text-sm">
      <div className="min-w-0">
        <div className="text-text-secondary truncate" title={input.name}>
          {componentLabel(input.name)}
        </div>
        <div className="text-caption text-text-muted truncate">{input.source}</div>
      </div>
      <div className="text-right font-mono tabular-nums text-text-primary">
        {formatNumber(input.value, { decimals: input.unit === "t/t" ? 2 : 0 })}
      </div>
      <div className="text-caption text-text-muted">{input.unit}</div>
    </div>
  );
}

function defaultSimulationInputs(model: CostModel): SimulationInputs {
  return {
    ironOreIndex: inputValue(model.inputs, "iron_ore_index_cny", 760),
    cokeProcessing: inputValue(model.inputs, "coking_processing_fee", 250),
    conversionFee: inputValue(model.inputs, "blast_furnace_conversion_fee", 760),
    thaiFieldLatex: inputValue(model.inputs, "thai_field_latex_cny", 11200),
    seasonalFactorPct: inputValue(model.inputs, "seasonal_factor_pct", 0.02),
    ruProcessingFee: inputValue(model.inputs, "ru_processing_fee", 950),
    rawRubberRatio: inputValue(model.inputs, "raw_rubber_ratio", 1.03),
    currentPrice: Math.round(model.current_price ?? model.total_unit_cost),
  };
}

function emptySimulationInputs(): SimulationInputs {
  return {
    ironOreIndex: 0,
    cokeProcessing: 0,
    conversionFee: 0,
    thaiFieldLatex: 0,
    seasonalFactorPct: 0,
    ruProcessingFee: 0,
    rawRubberRatio: 1,
    currentPrice: 0,
  };
}

function simulationInputsPayload(
  sector: SectorKey,
  values: SimulationInputs
): Record<string, Record<string, number>> {
  if (sector === "rubber") {
    return {
      NR: {
        thai_field_latex_cny: values.thaiFieldLatex,
        seasonal_factor_pct: values.seasonalFactorPct,
      },
      RU: {
        raw_rubber_ratio: values.rawRubberRatio,
        ru_processing_fee: values.ruProcessingFee,
      },
    };
  }
  return {
    I: { iron_ore_index_cny: values.ironOreIndex },
    J: { coking_processing_fee: values.cokeProcessing },
    RB: { blast_furnace_conversion_fee: values.conversionFee },
  };
}

function inputValue(inputs: Record<string, CostInput>, key: string, fallback: number): number {
  return inputs[key]?.value ?? fallback;
}

function buildSignalRules(model: CostModel, history: CostSnapshot[]) {
  const price = model.current_price;
  const latestMargin = model.profit_margin;
  const historyMargins = history.map(costSnapshotMargin);
  const recentMargins = historyMargins.slice(0, 10);
  const persistentNegative =
    recentMargins.length >= 10 && recentMargins.every((margin) => margin < -0.05);
  const crossedPositive =
    latestMargin !== null &&
    latestMargin > 0 &&
    historyMargins.slice(1, 8).some((margin) => margin < 0);

  return [
    {
      condition: "价格跌破 P50 中位成本",
      trigger: "median_pressure",
      active: price !== null && price < model.breakevens.p50,
      severity: "high" as const,
    },
    {
      condition: "价格跌破 P75 高成本线",
      trigger: "marginal_capacity_squeeze",
      active: price !== null && price < model.breakevens.p75,
      severity: "high" as const,
    },
    {
      condition: "价格跌破 P90 边际产能线",
      trigger: "marginal_capacity_squeeze",
      active: price !== null && price < model.breakevens.p90,
      severity: "medium" as const,
    },
    {
      condition: "利润率 < -5% 持续 2 周",
      trigger: "capacity_contraction",
      active: persistentNegative,
      severity: "high" as const,
    },
    {
      condition: "利润率由负转正",
      trigger: "restart_expectation",
      active: crossedPositive,
      severity: "medium" as const,
    },
  ];
}

function costSnapshotMargin(row: CostSnapshot): number {
  if (row.profit_margin !== null) return row.profit_margin;
  if (row.current_price === null || row.current_price <= 0) return 0;
  return (row.current_price - row.total_unit_cost) / row.current_price;
}

function profitBadge(model: CostModel): { label: string; variant: "up" | "down" | "neutral" } {
  if (model.profit_margin === null) return { label: "利润率 N/A", variant: "neutral" };
  return {
    label: `利润率 ${formatNumber(model.profit_margin * 100, { decimals: 2, signed: true })}%`,
    variant: model.profit_margin >= 0 ? "up" : "down",
  };
}

function symbolLabel(symbol: string): string {
  return SYMBOL_META[symbol]?.label ?? symbol;
}

function componentLabel(name: string): string {
  const labels: Record<string, string> = {
    iron_ore_index_cny: "铁矿石指数",
    coking_processing_fee: "焦炭加工费",
    blast_furnace_conversion_fee: "高炉加工费",
    thai_field_latex_cny: "泰国产区胶价",
    qingdao_bonded_spot_premium: "青岛保税区升水",
    hainan_yunnan_collection_cost: "海南/云南收胶成本",
    primary_processing_fee: "初加工费",
    ocean_freight: "进口运费",
    import_tax_vat_fee: "进口税费",
    seasonal_premium: "季节性溢价",
    seasonal_factor_pct: "季节性因子",
    upstream_nr_charge: "NR 原料成本",
    upstream_nr_unit_cost: "NR 单位成本",
    raw_rubber_ratio: "原胶折耗",
    ru_processing_fee: "RU 加工费",
    grade_premium: "交割等级升水",
    warehouse_finance_fee: "仓储资金费",
    exchange_delivery_fee: "交易所交割费",
    loss_adjustment_fee: "损耗调整费",
  };
  if (labels[name]) return labels[name];
  return name
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function rubberSeasonalityLabel(factor: number): { title: string } {
  if (factor >= 0.055) return { title: "停割期" };
  if (factor >= 0.035) return { title: "低供给" };
  if (factor >= 0.015) return { title: "开割初期" };
  if (factor < 0) return { title: "旺割期" };
  return { title: "平稳期" };
}

function metricLabel(metric: string): string {
  const labels: Record<string, string> = {
    breakeven_p50: "P50 中位成本",
    breakeven_p75: "P75 高成本",
    breakeven_p90: "P90 边际产能",
  };
  return labels[metric] ?? componentLabel(metric);
}

function recommendationLabel(report: CostQualityReport): { title: string; body: string } {
  if (report.paid_data_recommendation === "defer_paid_purchase_monitor_weekly") {
    return {
      title: "暂缓采购，周度复核",
      body: "当前公开源降级方案通过误差和历史触发评估，可以继续小步扩展，但保留每周复核和供应商试用入口。",
    };
  }
  if (report.paid_data_recommendation === "buy_paid_feed_before_expanding_signals") {
    return {
      title: "先采购再扩展信号",
      body: `${report.preferred_vendor ?? "Mysteel"} 优先级最高；当前历史触发稳定性不足，不宜继续扩大自动告警覆盖。`,
    };
  }
  return {
    title: "采购以提升精度",
    body: `${report.preferred_vendor ?? "SMM"} 可优先试用；公开源信号可用，但精细化分位和低频参数需要付费源校准。`,
  };
}

function formatCurrency(value: number): string {
  return `¥${formatNumber(value, { decimals: 0 })}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
