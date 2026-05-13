"use client";

import { useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";
import { Activity, CheckCircle2, Network } from "lucide-react";
import { CausalWeb } from "@/components/CausalWeb";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import type { CausalEdge, CausalNode } from "@/lib/domain";
import { fetchCausalWebGraph } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  normalizeNavigationScopeSource,
  normalizeNavigationSymbol,
  type NavigationScopeSource,
} from "@/lib/navigation-scope";

type CausalWebScope = {
  source: NavigationScopeSource | null;
  symbol: string | null;
  region: string | null;
  event: string | null;
};

export default function CausalWebPage() {
  const [nodes, setNodes] = useState<CausalNode[]>([]);
  const [edges, setEdges] = useState<CausalEdge[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [scope, setScope] = useState<CausalWebScope | null>(null);
  const { text } = useI18n();
  const activeCount = useMemo(
    () => nodes.filter((node) => node.active).length,
    [nodes]
  );
  const verifiedCount = useMemo(
    () => edges.filter((edge) => edge.verified).length,
    [edges]
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setScope({
      source: normalizeNavigationScopeSource(params.get("source")),
      symbol: normalizeNavigationSymbol(params.get("symbol")) || null,
      region: params.get("region")?.trim() || null,
      event: params.get("event")?.trim() || null,
    });
  }, []);

  useEffect(() => {
    if (scope === null) return;
    let mounted = true;
    fetchCausalWebGraph({ limit: 10, symbol: scope.symbol, region: scope.region, event: scope.event })
      .then((graph) => {
        if (!mounted) return;
        setNodes(graph.nodes);
        setEdges(graph.edges);
        setSource("runtime");
      })
      .catch(() => {
        if (mounted) setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, [scope]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-col gap-2 border-b border-border-subtle bg-bg-base/80 px-5 py-2 shadow-inner-panel lg:min-h-[48px] lg:flex-row lg:items-center lg:justify-between lg:gap-4">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="text-h2 text-text-primary">{text("Causal Web")}</h1>
          <p className="hidden truncate text-xs text-text-secondary md:block">
            {text("实时观察事件间的因果传导。点击节点追溯上游 / 预测下游。")}
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <HeaderMetric icon={Network} label={text("Nodes")} value={`${nodes.length}`} />
          <HeaderMetric icon={Activity} label={text("Active")} value={`${activeCount}/${nodes.length}`} tone="emerald" />
          <HeaderMetric icon={CheckCircle2} label={text("Verified")} value={`${verifiedCount}/${edges.length}`} tone="cyan" />
          <DataSourceBadge state={source} compact />
        </div>
      </div>
      <div className="relative flex-1">
        <CausalWeb
          variant="full"
          nodes={nodes}
          edges={edges}
          focusedEventId={scope?.event}
          scopeSymbol={scope?.symbol}
          scopeRegion={scope?.region}
          scopeSource={scope?.source}
          emptyMessage={emptyCausalGraphMessage(source)}
        />
      </div>
    </div>
  );
}

function emptyCausalGraphMessage(source: DataSourceState): string {
  if (source === "loading") return "因果图谱加载中";
  if (source === "fallback") return "因果图谱接口暂不可用";
  return "当前暂无运行态因果图谱";
}

function HeaderMetric({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone?: "neutral" | "emerald" | "cyan";
}) {
  const toneClass =
    tone === "emerald"
      ? "border-brand-emerald/30 text-brand-emerald-bright"
      : tone === "cyan"
        ? "border-brand-cyan/30 text-brand-cyan"
        : "border-border-subtle text-text-secondary";

  return (
    <div className={`flex h-7 items-center gap-2 rounded-sm border bg-bg-base px-2.5 text-caption shadow-inner-panel ${toneClass}`}>
      <Icon className="h-3.5 w-3.5" />
      <span className="text-text-muted">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}
