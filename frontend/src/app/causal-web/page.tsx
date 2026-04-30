"use client";

import { CausalWeb } from "@/components/CausalWeb";

export default function CausalWebPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="px-8 py-4 border-b border-border-subtle">
        <h1 className="text-h1 text-text-primary">Causal Web</h1>
        <p className="text-sm text-text-secondary mt-1">
          实时观察事件间的因果传导。点击节点追溯上游 / 预测下游。
        </p>
      </div>
      <div className="flex-1 relative">
        <CausalWeb variant="full" />
      </div>
    </div>
  );
}
