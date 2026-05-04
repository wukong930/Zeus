"use client";

import { useEffect, useMemo, useState } from "react";
import { ALERTS, type Alert, type Severity } from "@/data/mock";
import { AlertCard } from "@/components/AlertCard";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { MetricTile } from "@/components/MetricTile";
import { fetchAlertsFromApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { AlertTriangle, RadioTower, Search, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";

const SECTORS = ["ferrous", "rubber", "energy", "metals", "agri", "precious"];

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [source, setSource] = useState<"loading" | "api" | "mock">("loading");
  const [enabledSeverities, setEnabledSeverities] = useState<Set<Severity>>(
    new Set(["critical", "high", "medium", "low"])
  );
  const [enabledSectors, setEnabledSectors] = useState<Set<string>>(new Set(SECTORS));

  useEffect(() => {
    let ignore = false;
    fetchAlertsFromApi()
      .then((rows) => {
        if (!ignore) {
          setAlerts(rows);
          setSource("api");
        }
      })
      .catch(() => {
        if (!ignore) {
          setAlerts(ALERTS);
          setSource("mock");
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const severities = useMemo(
    () =>
      (["critical", "high", "medium", "low"] as Severity[]).map((value) => ({
        value,
        label: value[0].toUpperCase() + value.slice(1),
        count: alerts.filter((alert) => alert.severity === value).length,
      })),
    [alerts]
  );

  const filtered = alerts.filter(
    (a) => enabledSeverities.has(a.severity) && enabledSectors.has(a.sector)
  );
  const criticalCount = alerts.filter((alert) => alert.severity === "critical").length;
  const manualCount = alerts.filter((alert) => alert.humanActionRequired).length;
  const verifiedCount = alerts.filter((alert) => alert.adversarialPassed).length;
  const { text } = useI18n();

  return (
    <div className="flex h-full">
      {/* Filter sidebar */}
      <aside className="w-80 overflow-y-auto border-r border-border-subtle bg-bg-surface/70 p-5 space-y-6">
        <div>
          <h1 className="text-h1 text-text-primary">{text("Alerts")}</h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-caption text-text-muted">
              {filtered.length} / {alerts.length}
            </p>
            <Badge variant={source === "mock" ? "orange" : "emerald"}>
              {source === "loading" ? "SYNC" : source.toUpperCase()}
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3">
          <MetricTile label={text("当前可见")} value={String(filtered.length)} caption={`${alerts.length} total`} icon={RadioTower} tone="cyan" />
          <MetricTile label="Critical" value={String(criticalCount)} caption="requires focus" icon={AlertTriangle} tone={criticalCount > 0 ? "down" : "neutral"} />
          <MetricTile label={text("已验证")} value={String(verifiedCount)} caption={`${manualCount} manual gates`} icon={ShieldCheck} tone="up" />
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            placeholder={text("搜索预警...")}
            className="w-full rounded-sm border border-border-default bg-bg-base pl-9 pr-3 h-9 text-sm focus:border-brand-emerald focus:outline-none focus:shadow-focus-ring"
          />
        </div>

        <div>
          <div className="text-caption text-text-muted uppercase tracking-wider mb-2">{text("严重度")}</div>
          <div className="space-y-1">
            {severities.map((s) => (
              <FilterChip
                key={s.value}
                checked={enabledSeverities.has(s.value)}
                onToggle={() => {
                  const next = new Set(enabledSeverities);
                  next.has(s.value) ? next.delete(s.value) : next.add(s.value);
                  setEnabledSeverities(next);
                }}
                label={
                  <span className="flex items-center gap-2 flex-1">
                    <Badge variant={s.value}>{s.label}</Badge>
                  </span>
                }
                count={s.count}
              />
            ))}
          </div>
        </div>

        <div>
          <div className="text-caption text-text-muted uppercase tracking-wider mb-2">{text("板块")}</div>
          <div className="space-y-1">
            {SECTORS.map((sec) => (
              <FilterChip
                key={sec}
                checked={enabledSectors.has(sec)}
                onToggle={() => {
                  const next = new Set(enabledSectors);
                  next.has(sec) ? next.delete(sec) : next.add(sec);
                  setEnabledSectors(next);
                }}
                label={text(sec)}
                count={alerts.filter((a) => a.sector === sec).length}
              />
            ))}
          </div>
        </div>
      </aside>

      {/* Alert stream */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        <div className="mb-4 flex items-center justify-between rounded-sm border border-border-subtle bg-bg-surface px-4 py-3 shadow-inner-panel">
          <div>
            <div className="text-h3 text-text-primary">{text("预警流")}</div>
            <div className="mt-1 text-caption text-text-muted">{text("按严重度、板块和人工确认状态扫描当前事件。")}</div>
          </div>
          <Badge variant={source === "mock" ? "orange" : "emerald"}>
            {source === "loading" ? "SYNC" : source.toUpperCase()}
          </Badge>
        </div>
        {filtered.length === 0 ? (
          <Card variant="flat" className="py-10 text-center text-text-muted">
            {source === "loading" ? text("预警加载中") : text("没有匹配的预警")}
          </Card>
        ) : (
          filtered.map((alert, i) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              glow={i === 0}
            />
          ))
        )}
      </div>
    </div>
  );
}

function FilterChip({
  checked,
  onToggle,
  label,
  count,
}: {
  checked: boolean;
  onToggle: () => void;
  label: React.ReactNode;
  count: number;
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "w-full flex items-center gap-2 px-3 h-8 rounded-sm border text-sm transition-colors",
        checked
          ? "border-border-default bg-bg-surface-raised text-text-primary shadow-inner-panel"
          : "border-transparent text-text-muted hover:border-border-subtle hover:bg-bg-surface-raised"
      )}
    >
      <div
        className={cn(
          "w-3.5 h-3.5 rounded-xs border flex items-center justify-center",
          checked
            ? "bg-brand-emerald border-brand-emerald"
            : "border-border-default"
        )}
      >
        {checked && <span className="text-white text-[10px] font-bold">✓</span>}
      </div>
      <span className="flex-1 text-left capitalize">{label}</span>
      <span className="text-caption text-text-muted font-mono">{count}</span>
    </button>
  );
}
