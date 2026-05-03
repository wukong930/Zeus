"use client";

import { useEffect, useMemo, useState } from "react";
import { ALERTS, type Alert, type Severity } from "@/data/mock";
import { AlertCard } from "@/components/AlertCard";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { fetchAlertsFromApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Search } from "lucide-react";

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

  return (
    <div className="flex h-full">
      {/* Filter sidebar */}
      <aside className="w-72 border-r border-border-subtle p-5 space-y-6 overflow-y-auto">
        <div>
          <h1 className="text-h1 text-text-primary">Alerts</h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-caption text-text-muted">
              {filtered.length} / {alerts.length}
            </p>
            <Badge variant={source === "mock" ? "orange" : "emerald"}>
              {source === "loading" ? "SYNC" : source.toUpperCase()}
            </Badge>
          </div>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            placeholder="搜索预警..."
            className="w-full bg-bg-surface border border-border-default rounded-sm pl-9 pr-3 h-9 text-sm focus:border-brand-emerald focus:outline-none"
          />
        </div>

        <div>
          <div className="text-caption text-text-muted uppercase tracking-wider mb-2">严重度</div>
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
          <div className="text-caption text-text-muted uppercase tracking-wider mb-2">板块</div>
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
                label={sec}
                count={alerts.filter((a) => a.sector === sec).length}
              />
            ))}
          </div>
        </div>
      </aside>

      {/* Alert stream */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {filtered.length === 0 ? (
          <Card variant="flat" className="py-10 text-center text-text-muted">
            {source === "loading" ? "预警加载中" : "没有匹配的预警"}
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
        "w-full flex items-center gap-2 px-3 h-8 rounded-sm text-sm transition-colors",
        checked ? "bg-bg-surface-raised text-text-primary" : "text-text-muted hover:bg-bg-surface-raised"
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
