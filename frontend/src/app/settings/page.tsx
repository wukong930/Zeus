"use client";

import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardSubtitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { MetricTile } from "@/components/MetricTile";
import { cn } from "@/lib/utils";
import { Bell, BrainCircuit, RadioTower, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import {
  fetchAlertDedupSettings,
  fetchDataSourceStatuses,
  fetchLLMProviderSettings,
  fetchLLMUsageSummary,
  fetchNotificationSettings,
  fetchSchedulerSnapshot,
  updateNotificationSettings,
  type AlertDedupSettings,
  type DataSourceStatus,
  type LLMProviderSettings,
  type LLMUsageSummary,
  type NotificationSettings,
  type NotificationSettingsUpdate,
  type SchedulerSnapshot,
} from "@/lib/api";

type NotificationKey = keyof NotificationSettingsUpdate;

export default function SettingsPage() {
  const { text } = useI18n();
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerSnapshot | null>(null);
  const [llmUsage, setLlmUsage] = useState<LLMUsageSummary | null>(null);
  const [llmUsageSource, setLlmUsageSource] = useState<DataSourceState>("loading");
  const [llmProviders, setLlmProviders] = useState<LLMProviderSettings[]>([]);
  const [llmProviderSource, setLlmProviderSource] = useState<DataSourceState>("loading");
  const [alertDedupSettings, setAlertDedupSettings] = useState<AlertDedupSettings | null>(null);
  const [alertDedupSource, setAlertDedupSource] = useState<DataSourceState>("loading");
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [notificationSource, setNotificationSource] = useState<DataSourceState>("loading");
  const [savingNotification, setSavingNotification] = useState<NotificationKey | null>(null);
  const readySources = dataSources.filter((source) => source.status === "ready").length;
  const degradedJobs = scheduler?.health.degraded_jobs.length ?? 0;
  const warningJobs = scheduler?.health.warning_jobs.length ?? 0;
  const unconfiguredJobs = scheduler?.health.unconfigured_jobs.length ?? 0;
  const schedulerIssues = degradedJobs + warningJobs + unconfiguredJobs;
  const enabledJobs = scheduler?.health.enabled_jobs ?? 0;
  const llmUsageCaption = llmUsage
    ? `${llmUsage.calls} ${text("本月调用")}`
    : text(llmUsageSource === "loading" ? "同步中" : "暂无用量数据");

  useEffect(() => {
    let mounted = true;
    fetchDataSourceStatuses()
      .then((rows) => {
        if (mounted) setDataSources(rows);
      })
      .catch(() => undefined);
    fetchSchedulerSnapshot()
      .then((snapshot) => {
        if (mounted) setScheduler(snapshot);
      })
      .catch(() => undefined);
    fetchLLMUsageSummary()
      .then((summary) => {
        if (!mounted) return;
        setLlmUsage(summary);
        setLlmUsageSource("api");
      })
      .catch(() => {
        if (mounted) setLlmUsageSource("fallback");
      });
    fetchLLMProviderSettings()
      .then((providers) => {
        if (!mounted) return;
        setLlmProviders(providers);
        setLlmProviderSource("api");
      })
      .catch(() => {
        if (!mounted) setLlmProviderSource("fallback");
      });
    fetchAlertDedupSettings()
      .then((settings) => {
        if (!mounted) return;
        setAlertDedupSettings(settings);
        setAlertDedupSource("api");
      })
      .catch(() => {
        if (mounted) setAlertDedupSource("fallback");
      });
    fetchNotificationSettings()
      .then((settings) => {
        if (!mounted) return;
        setNotificationSettings(settings);
        setNotificationSource("api");
      })
      .catch(() => {
        if (mounted) setNotificationSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  function toggleNotification(key: NotificationKey) {
    if (!notificationSettings || savingNotification) return;

    const previous = notificationSettings;
    const nextValue = !notificationSettings[key];
    const optimistic = { ...notificationSettings, [key]: nextValue };
    const update = { [key]: nextValue } as NotificationSettingsUpdate;

    setNotificationSettings(optimistic);
    setSavingNotification(key);
    updateNotificationSettings(update)
      .then((settings) => {
        setNotificationSettings(settings);
        setNotificationSource("api");
      })
      .catch(() => {
        setNotificationSettings(previous);
        setNotificationSource("fallback");
      })
      .finally(() => {
        setSavingNotification(null);
      });
  }

  return (
    <div className="px-8 py-6 space-y-6 max-w-5xl animate-fade-in">
      <div>
        <h1 className="text-h1 text-text-primary">{text("设置")}</h1>
        <p className="text-sm text-text-secondary mt-1">{text("系统配置 · LLM 供应商 · 通知渠道")}</p>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile label={text("数据源")} value={`${readySources}/${dataSources.length || 6}`} caption={text("就绪")} icon={RadioTower} tone="cyan" />
        <MetricTile label={text("调度任务")} value={`${enabledJobs}`} caption={schedulerIssues ? `${schedulerIssues} ${text("需要关注")}` : text("健康")} icon={ShieldCheck} tone={schedulerIssues ? "warning" : "up"} />
        <MetricTile
          label={text("LLM 月度成本")}
          value={formatUsd(llmUsage?.estimated_cost_usd)}
          caption={llmUsageCaption}
          icon={BrainCircuit}
          tone="violet"
        />
        <MetricTile
          label={text("每日预警上限")}
          value={alertDedupSettings ? String(alertDedupSettings.daily_alert_limit) : "--"}
          caption={text(alertDedupSource === "api" ? "运行态配置" : alertDedupSource === "loading" ? "配置同步中" : "接口不可用")}
          icon={Bell}
          tone={alertDedupSource === "api" ? "up" : "warning"}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>{text("数据源健康")}</CardTitle>
              <CardSubtitle>{text("免费源 / 注册源配置状态")}</CardSubtitle>
            </div>
          </CardHeader>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(dataSources.length ? dataSources : []).map((source) => (
              <HealthRow
                key={source.id}
                label={source.name}
                value={statusLabel(source.status)}
                ok={source.status === "ready"}
              />
            ))}
          </div>
        </Card>

        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>{text("调度运行态")}</CardTitle>
              <CardSubtitle>{text("最近任务状态与未配置项")}</CardSubtitle>
            </div>
          </CardHeader>
          <div className="space-y-2">
            {scheduler?.jobs.slice(0, 6).map((job) => (
              <HealthRow
                key={job.id}
                label={job.name}
                value={statusLabel(job.last_result ?? job.status)}
                ok={job.status === "ok" && job.last_error === null}
              />
            ))}
            {scheduler && scheduler.health.unconfigured_jobs.length > 0 && (
              <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-caption text-text-muted shadow-inner-panel">
                {text("未配置")}：{scheduler.health.unconfigured_jobs.join(", ")}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>{text("LLM 供应商")}</CardTitle>
            <CardSubtitle>{text("多供应商支持，按场景路由")}</CardSubtitle>
          </div>
          <DataSourceBadge state={llmProviderSource} compact />
        </CardHeader>
        <div className="space-y-3">
          <div className="rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">{text("Alert Agent 用量")}</div>
                <div className="text-caption text-text-muted">
                  {llmUsage
                    ? `${llmUsage.period_start} → ${llmUsage.period_end}`
                    : text("等待后端用量同步")}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-sm text-text-primary tabular-nums">
                  {formatUsd(llmUsage?.estimated_cost_usd)}
                </div>
                <div className="text-caption text-text-muted">
                  {llmUsage
                    ? `${llmUsage.calls} ${text("调用")} · ${llmUsage.cache_hits} ${text("缓存命中")}`
                    : text("暂无用量数据")}
                </div>
              </div>
            </div>
          </div>
          {llmProviders.map((p) => (
            <div key={p.provider} className="flex items-center gap-3 rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{p.name}</span>
                  {p.active && <Badge variant="emerald">{text("主力")}</Badge>}
                  {!p.configured && <Badge variant="orange">{text("未配置")}</Badge>}
                </div>
                <div className="text-caption text-text-muted font-mono">{p.model ?? text("未配置 Key")}</div>
              </div>
              <div className="text-right text-sm">
                <div className="text-text-secondary font-mono tabular-nums">
                  {text(providerRouteLabel(p))}
                </div>
                <div className="text-caption text-text-muted">{text(providerSourceLabel(p.source))}</div>
              </div>
              <Button variant="secondary" size="sm" disabled>{text("配置")}</Button>
            </div>
          ))}
          {llmProviderSource === "fallback" && (
            <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm text-text-secondary shadow-inner-panel">
              {text("LLM 供应商配置接口暂不可用")}
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>{text("通知渠道")}</CardTitle>
              <CardSubtitle>{text("前端实时推送与外部 Webhook")}</CardSubtitle>
            </div>
            <DataSourceBadge state={notificationSource} compact />
          </CardHeader>
          <div className="space-y-3 text-sm">
            <Toggle
              label="实时 SSE 推送（前端）"
              checked={Boolean(notificationSettings?.realtime_sse)}
              disabled={!notificationSettings || savingNotification !== null}
              onToggle={() => toggleNotification("realtime_sse")}
            />
            <Toggle
              label="飞书 Webhook"
              checked={Boolean(notificationSettings?.feishu_webhook)}
              disabled={!notificationSettings || savingNotification !== null}
              onToggle={() => toggleNotification("feishu_webhook")}
            />
            <Toggle
              label="Email 通知"
              checked={Boolean(notificationSettings?.email)}
              disabled={!notificationSettings || savingNotification !== null}
              onToggle={() => toggleNotification("email")}
            />
            <Toggle
              label="自定义 Webhook"
              checked={Boolean(notificationSettings?.custom_webhook)}
              disabled={!notificationSettings || savingNotification !== null}
              onToggle={() => toggleNotification("custom_webhook")}
            />
          </div>
        </Card>

        <Card variant="data">
          <CardHeader>
            <div>
              <CardTitle>{text("预警去重设置")}</CardTitle>
              <CardSubtitle>{text("控制重复预警与升级重发")}</CardSubtitle>
            </div>
            <DataSourceBadge state={alertDedupSource} compact />
          </CardHeader>
          <div className="space-y-3 text-sm">
            <SettingRow
              label="同品种同方向 N 小时内只发一次"
              value={formatHours(alertDedupSettings?.repeat_window_hours)}
            />
            <SettingRow
              label="同信号组合 N 小时内只发一次"
              value={formatHours(alertDedupSettings?.combination_window_hours)}
            />
            <SettingRow
              label="每日预警上限"
              value={formatAlertLimit(alertDedupSettings?.daily_alert_limit)}
            />
            <SettingRow
              label="允许严重度升级时重新发送"
              value={alertDedupSettings ? (alertDedupSettings.allow_severity_upgrade_resend ? "是" : "否") : "--"}
            />
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
              v0.1.0 — {text("运行态版本")}。{text("当前版本已接入 Python 后端、事件总线、真实免费数据源、信号检测、校准循环、对抗引擎和 Alert Agent；接口不可用时会显示空态或降级状态，避免模拟数据冒充运行态结果。")}
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

function providerRouteLabel(provider: LLMProviderSettings): string {
  if (provider.active) return "主路由";
  if (provider.configured) return "候选";
  return "未配置";
}

function providerSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    database: "数据库配置",
    environment: "环境变量配置",
    not_configured: "缺少 Key",
  };
  return labels[source] ?? source;
}

function formatUsd(value?: number | null): string {
  if (value == null) return "--";
  return `$${value.toFixed(2)}`;
}

function formatHours(value?: number | null): string {
  return value == null ? "--" : `${value} 小时`;
}

function formatAlertLimit(value?: number | null): string {
  return value == null ? "--" : `${value} 条`;
}

function Toggle({
  label,
  checked,
  disabled,
  onToggle,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  const { text } = useI18n();

  return (
    <div className={cn(
      "flex min-h-10 items-center justify-between rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel",
      disabled && "opacity-65"
    )}>
      <span className="text-text-secondary">{text(label)}</span>
      <SwitchControl
        checked={checked}
        disabled={disabled}
        label={text(label)}
        onToggle={onToggle}
      />
    </div>
  );
}

function SwitchControl({
  checked,
  disabled = false,
  label,
  onToggle,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "relative inline-flex h-[28px] w-[54px] shrink-0 items-center rounded-full border p-[3px] transition-all duration-200 focus-visible:shadow-focus-ring focus-visible:outline-none disabled:cursor-not-allowed",
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

function HealthRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  const { text } = useI18n();

  return (
    <div className="flex items-center justify-between gap-3 rounded-sm border border-border-subtle bg-bg-base px-3 py-2 shadow-inner-panel">
      <span className="truncate text-sm text-text-secondary">{text(label)}</span>
      <Badge variant={ok ? "emerald" : "orange"}>{text(value)}</Badge>
    </div>
  );
}

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    ready: "就绪",
    ok: "正常",
    success: "成功",
    warning: "注意",
    disabled: "停用",
    degraded: "降级",
    skipped: "跳过",
    missing_key: "缺少 Key",
    missing_dependency: "缺少依赖",
    unconfigured: "未配置",
    failed: "失败",
  };
  return labels[value] ?? value;
}
