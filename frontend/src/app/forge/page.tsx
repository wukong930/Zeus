"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/Button";
import { Wrench, Plus } from "lucide-react";

export default function StrategyForgePage() {
  return (
    <div className="px-8 py-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Strategy Forge</h1>
        <p className="text-sm text-text-secondary mt-1">策略研究、回测、参数调优 · vectorbt + DoWhy</p>
      </div>

      <Card variant="flat">
        <EmptyState
          icon={<Wrench className="w-16 h-16" />}
          title="还没有策略"
          description="从模板创建策略（均值回归 / 动量突破 / 通道突破 / 事件驱动），或导入你已有的逻辑"
          action={
            <div className="flex gap-2">
              <Button variant="action">
                <Plus className="w-4 h-4" />
                从模板创建
              </Button>
              <Button variant="secondary">导入策略</Button>
            </div>
          }
        />
      </Card>
    </div>
  );
}
