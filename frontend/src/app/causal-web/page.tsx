"use client";

import type { ComponentType } from "react";
import { Activity, CheckCircle2, Network } from "lucide-react";
import { CausalWeb } from "@/components/CausalWeb";
import { CAUSAL_EDGES, CAUSAL_NODES } from "@/data/mock";

export default function CausalWebPage() {
  const activeCount = CAUSAL_NODES.filter((node) => node.active).length;
  const verifiedCount = CAUSAL_EDGES.filter((edge) => edge.verified).length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-col gap-2 border-b border-border-subtle bg-bg-base/80 px-5 py-2 shadow-inner-panel lg:min-h-[48px] lg:flex-row lg:items-center lg:justify-between lg:gap-4">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="text-h2 text-text-primary">Causal Web</h1>
          <p className="hidden truncate text-xs text-text-secondary md:block">
            实时观察事件间的因果传导。点击节点追溯上游 / 预测下游。
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <HeaderMetric icon={Network} label="Nodes" value={`${CAUSAL_NODES.length}`} />
          <HeaderMetric icon={Activity} label="Active" value={`${activeCount}/${CAUSAL_NODES.length}`} tone="emerald" />
          <HeaderMetric icon={CheckCircle2} label="Verified" value={`${verifiedCount}/${CAUSAL_EDGES.length}`} tone="cyan" />
        </div>
      </div>
      <div className="relative flex-1">
        <CausalWeb variant="full" />
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
