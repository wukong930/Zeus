"use client";

import { useEffect, useState } from "react";
import { HEARTBEAT_STATE, REGIME_LABEL } from "@/data/mock";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

const dot = (status: "healthy" | "warning" | "alert") =>
  status === "healthy"
    ? "bg-brand-emerald-bright shadow-glow-emerald"
    : status === "warning"
    ? "bg-severity-high-fg"
    : "bg-data-down shadow-glow-red animate-glow-pulse";

export function HeartbeatBar() {
  const s = HEARTBEAT_STATE;
  const { lang, text } = useI18n();
  const [clock, setClock] = useState("--:--:--");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const updateClock = () => {
      setClock(new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Shanghai" }));
    };
    setMounted(true);
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="h-8 w-full bg-bg-base border-b border-border-subtle flex items-center gap-5 px-5 text-caption text-text-muted overflow-x-auto">
      <Item dotClass={dot("healthy")} label={text("数据")} value={lang === "zh" ? `${s.dataAge}前` : `${s.dataAge} ago`} />
      <Item dotClass={dot("healthy")} label={text("活跃")} value={lang === "zh" ? `${s.activeSignals} 个信号` : `${s.activeSignals} signals`} />
      <Item
        dotClass={dot(s.driftStatus)}
        label={text("漂移")}
        value={text(s.drift)}
      />
      <Item
        dotClass={dot("healthy")}
        label={text("校准")}
        value={`${s.calibrationProgress}/${s.calibrationTarget}`}
      />
      <Item dotClass={dot("healthy")} label={text("状态")} value={text(REGIME_LABEL[s.regime] ?? s.regime)} />
      <div className="ml-auto text-text-muted">
        <span suppressHydrationWarning className="font-mono tabular-nums">
          {mounted ? clock : "--:--:--"}
        </span>
      </div>
    </div>
  );
}

function Item({ dotClass, label, value }: { dotClass: string; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      <div className={cn("w-1.5 h-1.5 rounded-full animate-heartbeat", dotClass)} />
      <span className="text-text-muted">{label}</span>
      <span className="text-text-secondary font-medium">{value}</span>
    </div>
  );
}
