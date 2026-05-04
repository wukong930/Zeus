"use client";

import { CausalWeb } from "@/components/CausalWeb";

export default function CausalWebPage() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-col gap-1 border-b border-border-subtle px-6 py-2.5 lg:min-h-[52px] lg:flex-row lg:items-end lg:justify-between lg:gap-4">
        <h1 className="text-h2 text-text-primary">Causal Web</h1>
        <p className="max-w-2xl text-xs text-text-secondary lg:pb-0.5 lg:text-right">
          实时观察事件间的因果传导。点击节点追溯上游 / 预测下游。
        </p>
      </div>
      <div className="relative flex-1">
        <CausalWeb variant="full" />
      </div>
    </div>
  );
}
