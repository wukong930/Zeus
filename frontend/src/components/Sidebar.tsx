"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Bell,
  Plane,
  Map as MapIcon,
  Network,
  Factory,
  Layers,
  Beaker,
  Wrench,
  NotebookPen,
  BarChart3,
  Settings,
  Newspaper,
  Globe2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { fetchAlertsFromApi } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "命令中心", icon: LayoutDashboard },
  { href: "/alerts", label: "预警", icon: Bell },
  { href: "/trade-plans", label: "交易计划", icon: Plane },
  { href: "/portfolio", label: "持仓地图", icon: MapIcon },
  { divider: true } as const,
  { href: "/causal-web", label: "因果网络", icon: Network },
  { href: "/world-map", label: "世界风险地图", icon: Globe2 },
  { href: "/news", label: "新闻事件", icon: Newspaper },
  { href: "/industry", label: "产业透镜", icon: Factory },
  { href: "/sectors", label: "板块", icon: Layers },
  { href: "/future-lab", label: "未来实验室", icon: Beaker },
  { divider: true } as const,
  { href: "/forge", label: "策略锻造", icon: Wrench },
  { href: "/notebook", label: "笔记本", icon: NotebookPen },
  { href: "/analytics", label: "分析", icon: BarChart3 },
  { divider: true } as const,
  { href: "/settings", label: "设置", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { text } = useI18n();
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const brandTagline = text("Trades are won before they begin");

  useEffect(() => {
    let cancelled = false;

    fetchAlertsFromApi()
      .then((alerts) => {
        if (!cancelled) setAlertCount(alerts.length);
      })
      .catch(() => {
        if (!cancelled) setAlertCount(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <aside className="flex h-full w-[188px] shrink-0 flex-col border-r border-border-subtle bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] shadow-inner-panel">
      <div className="flex h-12 select-none items-center gap-2.5 border-b border-border-subtle px-3">
        <Logo />
        <div className="flex flex-col leading-none">
          <span className="text-sm font-bold tracking-wider text-text-primary">ZEUS</span>
          <span className="max-w-[132px] text-[9px] font-medium leading-[1.08] text-text-muted" title={brandTagline}>
            {brandTagline}
          </span>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAV_ITEMS.map((item, idx) => {
          if ("divider" in item) {
            return <div key={idx} className="mx-2 my-1.5 h-px bg-border-subtle" />;
          }
          const Icon = item.icon;
          const active = pathname === item.href;
          const badge = item.href === "/alerts" ? formatAlertCount(alertCount) : null;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative mb-0.5 flex h-8 items-center gap-2 rounded-sm border px-2 text-xs font-medium transition-all duration-150",
                active
                  ? "border-brand-emerald/35 bg-brand-emerald/12 text-text-primary shadow-inner-panel"
                  : "border-transparent text-text-secondary hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-r-sm bg-brand-emerald" />
              )}
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-xs border",
                  active
                    ? "border-brand-emerald/35 bg-brand-emerald/15 text-brand-emerald-bright"
                    : "border-border-subtle bg-bg-base text-text-muted group-hover:text-text-primary"
                )}
              >
                <Icon className="h-3 w-3" strokeWidth={1.75} />
              </span>
              <span className="min-w-0 flex-1 truncate">{text(item.label)}</span>
              {badge && (
                <span className="inline-flex h-4 items-center rounded-xs bg-brand-orange px-1.5 text-caption font-semibold text-white shadow-glow-orange">
                  {badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border-subtle p-2">
        <div className="rounded-sm border border-border-subtle bg-bg-base px-2 py-2 shadow-inner-panel">
          <div className="flex items-center gap-2 text-caption text-text-muted">
            <div className="h-1.5 w-1.5 rounded-full bg-brand-emerald-bright shadow-glow-emerald animate-heartbeat" />
            <span>v0.1.0 {text("运行态")}</span>
          </div>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-bg-surface-raised">
            <div className="h-full w-2/3 rounded-full bg-brand-emerald" />
          </div>
        </div>
      </div>
    </aside>
  );
}

function formatAlertCount(count: number | null): string | null {
  if (count === null || count <= 0) return null;
  return count > 99 ? "99+" : String(count);
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="zeusGrad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="#10B981" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
      </defs>
      <rect x="3" y="3" width="26" height="26" rx="4" stroke="url(#zeusGrad)" strokeWidth="1.5" fill="none" />
      <path
        d="M9 9 L23 9 L9 23 L23 23"
        stroke="url(#zeusGrad)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="16" cy="16" r="2" fill="#F97316" />
    </svg>
  );
}
