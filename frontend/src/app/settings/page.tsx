"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { MetricTile } from "@/components/MetricTile";
import { cn } from "@/lib/utils";
import { Bell, BrainCircuit, RadioTower, ShieldCheck } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="px-8 py-6 space-y-6 max-w-5xl animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Settings</h1>
        <p className="text-sm text-text-secondary mt-1">系统配置 · LLM 供应商 · 通知渠道</p>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="LLM Routes" value="3" caption="active providers" icon={BrainCircuit} tone="violet" />
        <MetricTile label="Push Channels" value="2/4" caption="realtime enabled" icon={RadioTower} tone="cyan" />
        <MetricTile label="Dedup Window" value="12h" caption="symbol direction" icon={ShieldCheck} tone="up" />
        <MetricTile label="Alert Budget" value="50" caption="daily cap" icon={Bell} tone="warning" />
      </div>

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>LLM 供应商</CardTitle>
            <CardSubtitle>多供应商支持，按场景路由</CardSubtitle>
          </div>
        </CardHeader>
        <div className="space-y-3">
          {[
            { name: "Anthropic Claude", model: "claude-sonnet-4-6", status: "active", usage: "$18.20 / $50" },
            { name: "OpenAI", model: "gpt-4o", status: "configured", usage: "$6.10 / $30" },
            { name: "DeepSeek", model: "deepseek-chat", status: "configured", usage: "$0.05 / $5" },
          ].map((p) => (
            <div key={p.name} className="flex items-center gap-3 rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{p.name}</span>
                  {p.status === "active" && <Badge variant="emerald">主力</Badge>}
                </div>
                <div className="text-caption text-text-muted font-mono">{p.model}</div>
              </div>
              <div className="text-right text-sm">
                <div className="text-text-secondary font-mono tabular-nums">{p.usage}</div>
                <div className="text-caption text-text-muted">本月成本 / 预算</div>
              </div>
              <Button variant="secondary" size="sm">配置</Button>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>通知渠道</CardTitle>
              <CardSubtitle>前端实时推送与外部 Webhook</CardSubtitle>
            </div>
          </CardHeader>
          <div className="space-y-3 text-sm">
            <Toggle label="实时 SSE 推送（前端）" enabled />
            <Toggle label="飞书 Webhook" enabled />
            <Toggle label="Email 通知" />
            <Toggle label="自定义 Webhook" />
          </div>
        </Card>

        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>预警去重设置</CardTitle>
              <CardSubtitle>控制重复预警与升级重发</CardSubtitle>
            </div>
          </CardHeader>
          <div className="space-y-3 text-sm">
            <SettingRow label="同品种同方向 N 小时内只发一次" value="12 小时" />
            <SettingRow label="同信号组合 N 小时内只发一次" value="24 小时" />
            <SettingRow label="每日预警上限" value="50 条" />
            <SettingRow label="允许严重度升级时重新发送" value="是" />
          </div>
        </Card>
      </div>

      <Card variant="data" className="border-l-[3px] border-l-brand-emerald">
        <div className="flex items-start justify-between gap-5">
          <div>
            <div className="text-h3 mb-1">关于 Zeus</div>
            <p className="italic text-brand-emerald-bright text-sm mb-3">
              Trades are won before they begin.
            </p>
            <p className="text-sm text-text-secondary">
              v0.1.0 — Prototype Demo. 这个版本是纯前端原型，所有数据为模拟。后端 Python 服务（事件总线、信号检测、校准循环、对抗引擎、Alert Agent）将在 Phase 1 开始构建。
            </p>
          </div>
          <div className="hidden rounded-sm border border-brand-emerald/30 bg-brand-emerald/10 px-3 py-2 font-mono text-caption text-brand-emerald-bright md:block">
            ZEUS · DESIGN
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <Badge variant="emerald">design v1.0</Badge>
          <Badge>arch v1.2</Badge>
          <Badge>plan v1.2</Badge>
        </div>
      </Card>
    </div>
  );
}

function Toggle({ label, enabled = false }: { label: string; enabled?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel">
      <span className="text-text-secondary">{label}</span>
      <div
        className={cn(
          "relative h-5 w-9 rounded-full border transition-colors",
          enabled ? "border-brand-emerald/40 bg-brand-emerald shadow-glow-emerald" : "border-border-default bg-bg-surface-raised"
        )}
      >
        <div
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
            enabled ? "translate-x-[18px]" : "translate-x-0.5"
          )}
        />
      </div>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel">
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}
