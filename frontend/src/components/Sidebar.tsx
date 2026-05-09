"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Beaker,
  Bell,
  ChevronLeft,
  ChevronRight,
  Factory,
  Globe2,
  Layers,
  LayoutDashboard,
  Map as MapIcon,
  Network,
  Newspaper,
  NotebookPen,
  Plane,
  Settings,
  Wrench,
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

type SidebarPreference = "auto" | "collapsed" | "expanded";
type SidebarTooltip = {
  label: string;
  badge: string | null;
  top: number;
};

const SIDEBAR_MODE_STORAGE_KEY = "zeus-sidebar-mode";
const LEGACY_SIDEBAR_STORAGE_KEY = "zeus-sidebar-collapsed";
const IMMERSIVE_ROUTES = ["/world-map", "/causal-web"];

export function Sidebar() {
  const pathname = usePathname();
  const { lang, text } = useI18n();
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [preference, setPreference] = useState<SidebarPreference>("auto");
  const [tooltip, setTooltip] = useState<SidebarTooltip | null>(null);
  const [ready, setReady] = useState(false);
  const brandTagline = lang === "zh" ? "交易胜于未始" : "Trades are won before they begin";
  const routePrefersCollapsed = isImmersiveRoute(pathname);
  const collapsed = preference === "auto" ? routePrefersCollapsed : preference === "collapsed";

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

  useEffect(() => {
    const savedMode = window.localStorage.getItem(SIDEBAR_MODE_STORAGE_KEY);
    if (isSidebarPreference(savedMode)) {
      setPreference(savedMode);
    } else {
      const legacyCollapsed = window.localStorage.getItem(LEGACY_SIDEBAR_STORAGE_KEY);
      setPreference(legacyCollapsed === "true" ? "collapsed" : "auto");
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    window.localStorage.setItem(SIDEBAR_MODE_STORAGE_KEY, preference);
  }, [preference, ready]);

  useEffect(() => {
    if (!collapsed) setTooltip(null);
  }, [collapsed]);

  function showTooltip(label: string, badge: string | null, target: HTMLElement) {
    if (!collapsed) return;
    const asideTop = target.closest("aside")?.getBoundingClientRect().top ?? 0;
    const rect = target.getBoundingClientRect();
    setTooltip({
      label: text(label),
      badge,
      top: rect.top - asideTop + rect.height / 2,
    });
  }

  return (
    <aside
      className={cn(
        "group/sidebar relative flex h-full shrink-0 flex-col border-r border-white/[0.07] bg-black/58 shadow-[0_18px_70px_rgba(0,0,0,0.42),inset_1px_0_0_rgba(255,255,255,0.035)] backdrop-blur-xl transition-[width] duration-200 ease-standard",
        collapsed ? "w-[64px]" : "w-[188px]"
      )}
      data-sidebar-collapsed={collapsed}
      data-sidebar-mode={preference}
      data-sidebar-immersive={routePrefersCollapsed}
    >
      <div
        className={cn(
          "flex h-12 select-none items-center border-b border-white/[0.06] px-3",
          collapsed ? "justify-center" : "gap-2.5"
        )}
      >
        <Logo collapsed={collapsed} />
        <div className={cn("min-w-0 flex-col leading-none", collapsed ? "hidden" : "flex")}>
          <span className="text-sm font-bold tracking-wider text-text-primary">ZEUS</span>
          <span className="max-w-[132px] text-[9px] font-medium leading-[1.08] text-text-muted" title={brandTagline}>
            {brandTagline}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={() => setPreference(collapsed ? "expanded" : "collapsed")}
        className="absolute -right-3 top-3 z-20 flex h-6 w-6 items-center justify-center rounded-full border border-white/[0.09] bg-black/78 text-text-muted shadow-data-panel backdrop-blur-md transition-colors hover:border-brand-emerald/35 hover:text-text-primary"
        aria-label={collapsed ? text("展开侧边栏") : text("收起侧边栏")}
        title={collapsed ? text("展开侧边栏") : text("收起侧边栏")}
      >
        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
      </button>
      <nav className={cn("flex-1 overflow-y-auto py-2", collapsed ? "px-2" : "px-2")}>
        {NAV_ITEMS.map((item, idx) => {
          if ("divider" in item) {
            return (
              <div
                key={idx}
                className={cn("my-1.5 h-px bg-white/[0.07]", collapsed ? "mx-2" : "mx-2")}
              />
            );
          }
          const Icon = item.icon;
          const active = pathname === item.href;
          const badge = item.href === "/alerts" ? formatAlertCount(alertCount) : null;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-label={text(item.label)}
              onMouseEnter={(event) => showTooltip(item.label, badge, event.currentTarget)}
              onMouseLeave={() => setTooltip(null)}
              onFocus={(event) => showTooltip(item.label, badge, event.currentTarget)}
              onBlur={() => setTooltip(null)}
              className={cn(
                "group relative mb-0.5 flex h-8 items-center rounded-sm border text-xs font-medium transition-all duration-150",
                collapsed ? "justify-center px-0" : "gap-2 px-2",
                active
                  ? "border-brand-emerald/35 bg-brand-emerald/14 text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.045),0_0_18px_rgba(16,185,129,0.1)]"
                  : "border-transparent text-text-secondary hover:border-white/[0.08] hover:bg-white/[0.055] hover:text-text-primary"
              )}
            >
              {active && (
                <span
                  className={cn(
                    "absolute rounded-r-sm bg-brand-emerald",
                    collapsed ? "left-0 top-2 bottom-2 w-[2px]" : "left-0 top-1.5 bottom-1.5 w-[2px]"
                  )}
                />
              )}
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-xs border",
                  active
                    ? "border-brand-emerald/35 bg-brand-emerald/15 text-brand-emerald-bright"
                    : "border-white/[0.08] bg-black/42 text-text-muted group-hover:text-text-primary"
                )}
              >
                <Icon className="h-3 w-3" strokeWidth={1.75} />
              </span>
              <span className={cn("min-w-0 flex-1 truncate", collapsed && "hidden")}>{text(item.label)}</span>
              {badge && (
                <span
                  className={cn(
                    "inline-flex h-4 items-center rounded-xs bg-brand-orange px-1.5 text-caption font-semibold text-white shadow-glow-orange",
                    collapsed && "absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1"
                  )}
                >
                  {badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      {collapsed && tooltip && (
        <div
          data-testid="sidebar-collapsed-tooltip"
          className="pointer-events-none absolute left-[calc(100%+10px)] z-50 flex items-center gap-2 rounded-sm border border-white/[0.09] bg-black/82 px-2.5 py-1.5 text-xs text-text-primary shadow-data-panel backdrop-blur-xl"
          style={{ top: tooltip.top, transform: "translateY(-50%)" }}
        >
          <span className="absolute -left-1 h-2 w-2 rotate-45 border-b border-l border-white/[0.09] bg-black/82" />
          <span className="relative whitespace-nowrap">{tooltip.label}</span>
          {tooltip.badge && (
            <span className="relative inline-flex h-4 items-center rounded-xs bg-brand-orange px-1.5 text-caption font-semibold text-white shadow-glow-orange">
              {tooltip.badge}
            </span>
          )}
        </div>
      )}
      <div className="border-t border-white/[0.06] p-2">
        <div
          className={cn(
            "rounded-sm border border-white/[0.08] bg-black/42 shadow-inner-panel",
            collapsed ? "flex h-10 items-center justify-center" : "px-2 py-2"
          )}
          title={collapsed ? `v0.1.0 ${text("运行态")}` : undefined}
        >
          <div className={cn("flex items-center text-caption text-text-muted", collapsed ? "justify-center" : "gap-2")}>
            <div className="h-1.5 w-1.5 rounded-full bg-brand-emerald-bright shadow-glow-emerald animate-heartbeat" />
            <span className={cn(collapsed && "hidden")}>v0.1.0 {text("运行态")}</span>
          </div>
          <div className={cn("mt-2 h-1 overflow-hidden rounded-full bg-bg-surface-raised", collapsed && "hidden")}>
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

function isImmersiveRoute(pathname: string | null): boolean {
  if (!pathname) return false;
  return IMMERSIVE_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

function isSidebarPreference(value: string | null): value is SidebarPreference {
  return value === "auto" || value === "collapsed" || value === "expanded";
}

function Logo({ collapsed }: { collapsed?: boolean }) {
  return (
    <svg
      width={collapsed ? "30" : "28"}
      height={collapsed ? "30" : "28"}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="shrink-0"
    >
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
