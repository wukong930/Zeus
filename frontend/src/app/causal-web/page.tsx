"use client";

import { useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";
import { Activity, CheckCircle2, Network } from "lucide-react";
import { CausalWeb } from "@/components/CausalWeb";
import { DataSourceBadge } from "@/components/DataSourceBadge";
import { CAUSAL_EDGES, CAUSAL_NODES } from "@/data/mock";
import type { CausalEdge, CausalNode } from "@/data/mock";
import { fetchCausalWebGraph } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function CausalWebPage() {
  const [nodes, setNodes] = useState<CausalNode[]>(CAUSAL_NODES);
  const [edges, setEdges] = useState<CausalEdge[]>(CAUSAL_EDGES);
  const [source, setSource] = useState<"runtime" | "fallback">("fallback");
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
    let mounted = true;
    fetchCausalWebGraph()
      .then((graph) => {
        if (!mounted || graph.nodes.length === 0) return;
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
  }, []);

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
        <CausalWeb variant="full" nodes={nodes} edges={edges} />
      </div>
    </div>
  );
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
