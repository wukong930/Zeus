"use client";

import { AlertTriangle, Database, Loader2, Radio } from "lucide-react";

import { Badge } from "@/components/Badge";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type DataSourceState = "loading" | "api" | "runtime" | "partial" | "mock" | "fallback";

type DataSourceBadgeProps = {
  state: DataSourceState;
  compact?: boolean;
  className?: string;
};

const SOURCE_META: Record<
  DataSourceState,
  {
    label: string;
    compactLabel: string;
    title: string;
    variant: "neutral" | "emerald" | "orange" | "cyan";
    icon: typeof Database;
  }
> = {
  loading: {
    label: "同步中",
    compactLabel: "同步",
    title: "正在从后端同步数据",
    variant: "neutral",
    icon: Loader2,
  },
  api: {
    label: "实时数据",
    compactLabel: "实时",
    title: "当前视图来自后端实时接口",
    variant: "emerald",
    icon: Database,
  },
  runtime: {
    label: "运行态数据",
    compactLabel: "运行态",
    title: "当前视图来自运行态图谱接口",
    variant: "emerald",
    icon: Radio,
  },
  partial: {
    label: "部分降级",
    compactLabel: "降级",
    title: "部分接口不可用，视图混合实时数据和降级结果",
    variant: "orange",
    icon: AlertTriangle,
  },
  mock: {
    label: "模拟数据",
    compactLabel: "模拟",
    title: "后端不可用时展示离线模拟数据",
    variant: "orange",
    icon: AlertTriangle,
  },
  fallback: {
    label: "回退数据",
    compactLabel: "回退",
    title: "当前视图使用本地回退样本",
    variant: "neutral",
    icon: AlertTriangle,
  },
};

export function DataSourceBadge({ state, compact = false, className }: DataSourceBadgeProps) {
  const { text } = useI18n();
  const meta = SOURCE_META[state];
  const Icon = meta.icon;

  return (
    <Badge
      variant={meta.variant}
      className={cn("gap-1.5", className)}
      title={text(meta.title)}
      aria-label={text(meta.title)}
    >
      <Icon className={cn("h-3 w-3", state === "loading" && "animate-spin")} />
      <span>{text(compact ? meta.compactLabel : meta.label)}</span>
    </Badge>
  );
}
