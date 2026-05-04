"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { MetricTile } from "@/components/MetricTile";
import { cn } from "@/lib/utils";
import { Bell, BrainCircuit, RadioTower, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function SettingsPage() {
  const { text } = useI18n();

  return (
    <div className="px-8 py-6 space-y-6 max-w-5xl animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">{text("设置")}</h1>
        <p className="text-sm text-text-secondary mt-1">{text("系统配置 · LLM 供应商 · 通知渠道")}</p>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile label={text("LLM 供应商")} value="4" caption="active providers" icon={BrainCircuit} tone="violet" />
        <MetricTile label={text("通知渠道")} value="2/4" caption="realtime enabled" icon={RadioTower} tone="cyan" />
        <MetricTile label={text("预警去重设置")} value="12h" caption="symbol direction" icon={ShieldCheck} tone="up" />
        <MetricTile label={text("每日预警上限")} value="50" caption="daily cap" icon={Bell} tone="warning" />
      </div>

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>{text("LLM 供应商")}</CardTitle>
            <CardSubtitle>{text("多供应商支持，按场景路由")}</CardSubtitle>
          </div>
        </CardHeader>
        <div className="space-y-3">
          {[
            { name: "xAI Grok", model: "grok-4.3", status: "active", usage: "$0.00 / $30" },
            { name: "Anthropic Claude", model: "claude-sonnet-4-6", status: "configured", usage: "$18.20 / $50" },
            { name: "OpenAI", model: "gpt-4o", status: "configured", usage: "$6.10 / $30" },
            { name: "DeepSeek", model: "deepseek-chat", status: "configured", usage: "$0.05 / $5" },
          ].map((p) => (
            <div key={p.name} className="flex items-center gap-3 rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{p.name}</span>
                  {p.status === "active" && <Badge variant="emerald">{text("主力")}</Badge>}
                </div>
                <div className="text-caption text-text-muted font-mono">{p.model}</div>
              </div>
              <div className="text-right text-sm">
                <div className="text-text-secondary font-mono tabular-nums">{p.usage}</div>
                <div className="text-caption text-text-muted">{text("本月成本 / 预算")}</div>
              </div>
              <Button variant="secondary" size="sm">{text("配置")}</Button>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>{text("通知渠道")}</CardTitle>
              <CardSubtitle>{text("前端实时推送与外部 Webhook")}</CardSubtitle>
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
              <CardTitle>{text("预警去重设置")}</CardTitle>
              <CardSubtitle>{text("控制重复预警与升级重发")}</CardSubtitle>
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
            <div className="text-h3 mb-1">{text("关于 Zeus")}</div>
            <p className="italic text-brand-emerald-bright text-sm mb-3">
              Trades are won before they begin.
            </p>
            <p className="text-sm text-text-secondary">
              v0.1.0 — Prototype Demo. {text("这个版本是纯前端原型，所有数据为模拟。后端 Python 服务（事件总线、信号检测、校准循环、对抗引擎、Alert Agent）将在 Phase 1 开始构建。")}
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
  const [checked, setChecked] = useState(enabled);
  const { text } = useI18n();

  return (
    <div className="flex min-h-10 items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel">
      <span className="text-text-secondary">{text(label)}</span>
      <SwitchControl
        checked={checked}
        label={text(label)}
        onToggle={() => setChecked((current) => !current)}
      />
    </div>
  );
}

function SwitchControl({
  checked,
  label,
  onToggle,
}: {
  checked: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onToggle}
      className={cn(
        "relative inline-flex h-[28px] w-[54px] shrink-0 items-center rounded-full border p-[3px] transition-all duration-200 focus-visible:shadow-focus-ring focus-visible:outline-none",
        checked
          ? "border-brand-emerald/55 bg-brand-emerald/90 shadow-[0_0_22px_rgba(16,185,129,0.28)]"
          : "border-border-default bg-[linear-gradient(180deg,rgba(31,31,31,0.95),rgba(8,8,8,0.98))]"
      )}
    >
      <span
        className={cn(
          "absolute left-[8px] font-mono text-[8px] font-semibold leading-none tracking-wide text-white/80 transition-opacity",
          checked ? "opacity-100" : "opacity-0"
        )}
      >
        ON
      </span>
      <span
        className={cn(
          "absolute right-[6px] font-mono text-[8px] font-semibold leading-none tracking-wide text-text-muted transition-opacity",
          checked ? "opacity-0" : "opacity-100"
        )}
      >
        OFF
      </span>
      <span
        className={cn(
          "relative z-10 h-[20px] w-[20px] rounded-full border transition-transform duration-200",
          checked
            ? "translate-x-[26px] border-white bg-white shadow-[0_4px_12px_rgba(0,0,0,0.32)]"
            : "translate-x-0 border-border-strong bg-text-secondary shadow-[0_3px_10px_rgba(0,0,0,0.45)]"
        )}
      />
    </button>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();

  return (
    <div className="flex items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel">
      <span className="text-text-secondary">{text(label)}</span>
      <span className="font-mono text-text-primary">{text(value)}</span>
    </div>
  );
}
