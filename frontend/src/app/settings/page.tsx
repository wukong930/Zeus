"use client";

import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";

export default function SettingsPage() {
  return (
    <div className="px-8 py-6 space-y-6 max-w-3xl animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">Settings</h1>
        <p className="text-sm text-text-secondary mt-1">系统配置 · LLM 供应商 · 通知渠道</p>
      </div>

      <Card variant="flat">
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
            <div key={p.name} className="flex items-center gap-3 py-3 border-b border-border-subtle last:border-b-0">
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

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>通知渠道</CardTitle>
          </div>
        </CardHeader>
        <div className="space-y-3 text-sm">
          <Toggle label="实时 SSE 推送（前端）" enabled />
          <Toggle label="飞书 Webhook" enabled />
          <Toggle label="Email 通知" />
          <Toggle label="自定义 Webhook" />
        </div>
      </Card>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>预警去重设置</CardTitle>
          </div>
        </CardHeader>
        <div className="space-y-3 text-sm">
          <SettingRow label="同品种同方向 N 小时内只发一次" value="12 小时" />
          <SettingRow label="同信号组合 N 小时内只发一次" value="24 小时" />
          <SettingRow label="每日预警上限" value="50 条" />
          <SettingRow label="允许严重度升级时重新发送" value="是" />
        </div>
      </Card>

      <Card variant="flat" className="border-l-[3px] border-l-brand-emerald">
        <div className="text-h3 mb-1">关于 Zeus</div>
        <p className="text-sm text-text-secondary">
          v0.1.0 — Prototype Demo. 这个版本是纯前端原型，所有数据为模拟。后端 Python 服务（事件总线、信号检测、校准循环、对抗引擎、Alert Agent）将在 Phase 1 开始构建。
        </p>
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
    <div className="flex items-center justify-between py-2 border-b border-border-subtle last:border-b-0">
      <span className="text-text-secondary">{label}</span>
      <div className={`w-9 h-5 rounded-full relative transition-colors ${enabled ? "bg-brand-emerald" : "bg-bg-surface-raised"}`}>
        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${enabled ? "translate-x-[18px]" : "translate-x-0.5"}`} />
      </div>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border-subtle last:border-b-0">
      <span className="text-text-secondary">{label}</span>
      <span className="text-text-primary font-mono">{value}</span>
    </div>
  );
}
