"use client";

import { useEffect, useState } from "react";
import {
  fetchCausalWebGraph,
  fetchDriftSnapshot,
  fetchSchedulerSnapshot,
  fetchThresholdCalibrationReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n, type Language } from "@/lib/i18n";

type RuntimeStatus = "healthy" | "warning" | "alert";

interface HeartbeatRuntimeState {
  refreshedAt: string | null;
  activeSignals: number | null;
  drift: string;
  driftStatus: RuntimeStatus;
  calibrationSamples: number | null;
  status: string;
  statusTone: RuntimeStatus;
}

const REFRESH_INTERVAL_MS = 30_000;

const dot = (status: RuntimeStatus) =>
  status === "healthy"
    ? "bg-brand-emerald-bright shadow-glow-emerald"
    : status === "warning"
    ? "bg-severity-high-fg"
    : "bg-data-down shadow-glow-red animate-glow-pulse";

export function HeartbeatBar() {
  const { lang, text } = useI18n();
  const [clock, setClock] = useState("--:--:--");
  const [now, setNow] = useState(() => new Date());
  const [mounted, setMounted] = useState(false);
  const [runtime, setRuntime] = useState<HeartbeatRuntimeState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const updateClock = () => {
      setNow(new Date());
      setClock(new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Shanghai" }));
    };
    setMounted(true);
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const snapshot = await fetchHeartbeatRuntimeState();
        if (!cancelled) setRuntime(snapshot);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const dataValue =
    loading
      ? text("同步中")
      : runtime?.refreshedAt
        ? formatAge(runtime.refreshedAt, now, lang)
        : "--";
  const activeSignals =
    runtime?.activeSignals === null || runtime?.activeSignals === undefined
      ? "--"
      : lang === "zh"
        ? `${runtime.activeSignals} 个信号`
        : `${runtime.activeSignals} signals`;
  const calibrationValue =
    runtime?.calibrationSamples === null || runtime?.calibrationSamples === undefined
      ? "--"
      : lang === "zh"
        ? `${runtime.calibrationSamples} 个样本`
        : `${runtime.calibrationSamples} samples`;

  return (
    <div className="h-8 w-full bg-bg-base border-b border-border-subtle flex items-center gap-5 px-5 text-caption text-text-muted overflow-x-auto">
      <Item dotClass={dot(runtime?.refreshedAt ? "healthy" : loading ? "warning" : "alert")} label={text("数据")} value={dataValue} />
      <Item dotClass={dot(runtime?.activeSignals === null || runtime?.activeSignals === undefined ? "warning" : "healthy")} label={text("活跃")} value={activeSignals} />
      <Item
        dotClass={dot(runtime?.driftStatus ?? "warning")}
        label={text("漂移")}
        value={text(runtime?.drift ?? "同步中")}
      />
      <Item
        dotClass={dot(runtime?.calibrationSamples === null || runtime?.calibrationSamples === undefined ? "warning" : "healthy")}
        label={text("校准")}
        value={calibrationValue}
      />
      <Item dotClass={dot(runtime?.statusTone ?? "warning")} label={text("状态")} value={text(runtime?.status ?? "同步中")} />
      <div className="ml-auto text-text-muted">
        <span suppressHydrationWarning className="font-mono tabular-nums">
          {mounted ? clock : "--:--:--"}
        </span>
      </div>
    </div>
  );
}

async function fetchHeartbeatRuntimeState(): Promise<HeartbeatRuntimeState> {
  const [graphResult, driftResult, calibrationResult, schedulerResult] = await Promise.allSettled([
    fetchCausalWebGraph(),
    fetchDriftSnapshot(),
    fetchThresholdCalibrationReport(),
    fetchSchedulerSnapshot(),
  ]);

  const graph = graphResult.status === "fulfilled" ? graphResult.value : null;
  const drift = driftResult.status === "fulfilled" ? driftResult.value : null;
  const calibration = calibrationResult.status === "fulfilled" ? calibrationResult.value : null;
  const scheduler = schedulerResult.status === "fulfilled" ? schedulerResult.value : null;
  const failedCount = [graphResult, driftResult, calibrationResult, schedulerResult].filter(
    (result) => result.status === "rejected"
  ).length;
  const schedulerDegraded = Boolean(
    scheduler?.health.degraded_jobs.length || scheduler?.health.unconfigured_jobs.length
  );

  return {
    refreshedAt: latestIso([graph?.generated_at, drift?.generated_at, drift?.latest_at]),
    activeSignals: graph
      ? graph.nodes.filter((node) => node.type === "signal" && node.active).length
      : null,
    drift: driftLabel(drift?.status),
    driftStatus: driftTone(drift?.status),
    calibrationSamples: calibration?.samples ?? null,
    status:
      failedCount === 4
        ? "接口降级"
        : failedCount > 0
          ? "部分降级"
          : schedulerDegraded
            ? "调度降级"
            : "运行态",
    statusTone: failedCount === 4 ? "alert" : failedCount > 0 || schedulerDegraded ? "warning" : "healthy",
  };
}

function latestIso(values: Array<string | null | undefined>): string | null {
  const timestamps = values
    .map((value) => (value ? Date.parse(value) : Number.NaN))
    .filter((value) => Number.isFinite(value));
  if (timestamps.length === 0) return null;
  return new Date(Math.max(...timestamps)).toISOString();
}

function driftLabel(status: string | null | undefined): string {
  if (status === "green") return "正常";
  if (status === "yellow") return "注意";
  if (status === "red") return "异常";
  if (status === "no_data") return "无漂移数据";
  return "不可用";
}

function driftTone(status: string | null | undefined): RuntimeStatus {
  if (status === "green") return "healthy";
  if (status === "yellow" || status === "no_data") return "warning";
  if (status === "red") return "alert";
  return "warning";
}

function formatAge(iso: string, now: Date, lang: Language): string {
  const timestamp = Date.parse(iso);
  if (!Number.isFinite(timestamp)) return "--";
  const seconds = Math.max(0, Math.floor((now.getTime() - timestamp) / 1000));
  if (seconds < 60) return lang === "zh" ? `${seconds}s 前` : `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return lang === "zh" ? `${minutes}m 前` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return lang === "zh" ? `${hours}h 前` : `${hours}h ago`;
}

function Item({ dotClass, label, value }: { dotClass: string; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      <div className={cn("w-1.5 h-1.5 rounded-full animate-heartbeat", dotClass)} />
      <span className="text-text-muted">{label}</span>
      <span className="text-text-secondary font-medium">{value}</span>
    </div>
  );
}
