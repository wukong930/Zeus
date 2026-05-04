"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Command Center", icon: LayoutDashboard },
  { href: "/alerts", label: "Alerts", icon: Bell, badge: 12 },
  { href: "/trade-plans", label: "Trade Plans", icon: Plane },
  { href: "/portfolio", label: "Portfolio Map", icon: MapIcon },
  { divider: true } as const,
  { href: "/causal-web", label: "Causal Web", icon: Network },
  { href: "/news", label: "News Events", icon: Newspaper },
  { href: "/industry", label: "Industry Lens", icon: Factory },
  { href: "/sectors", label: "Sectors", icon: Layers },
  { href: "/future-lab", label: "Future Lab", icon: Beaker },
  { divider: true } as const,
  { href: "/forge", label: "Strategy Forge", icon: Wrench },
  { href: "/notebook", label: "Notebook", icon: NotebookPen },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { divider: true } as const,
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-full w-[232px] shrink-0 flex-col border-r border-border-subtle bg-[linear-gradient(180deg,rgba(15,17,16,0.98),rgba(0,0,0,0.98))] shadow-inner-panel">
      <div className="flex h-16 select-none items-center gap-3 border-b border-border-subtle px-5">
        <Logo />
        <div className="flex flex-col leading-none">
          <span className="text-h3 font-bold tracking-wider text-text-primary">ZEUS</span>
          <span className="text-caption text-text-muted">Futures Intel</span>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item, idx) => {
          if ("divider" in item) {
            return <div key={idx} className="mx-3 my-3 h-px bg-border-subtle" />;
          }
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative mb-1 flex h-10 items-center gap-3 rounded-sm border px-3 text-sm font-medium transition-all duration-150",
                active
                  ? "border-brand-emerald/35 bg-brand-emerald/12 text-text-primary shadow-data-panel"
                  : "border-transparent text-text-secondary hover:border-border-subtle hover:bg-bg-surface-raised hover:text-text-primary"
              )}
            >
              {active && (
                <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-sm bg-brand-emerald" />
              )}
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-xs border",
                  active
                    ? "border-brand-emerald/35 bg-brand-emerald/15 text-brand-emerald-bright"
                    : "border-border-subtle bg-bg-base text-text-muted group-hover:text-text-primary"
                )}
              >
                <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>
              <span className="flex-1">{item.label}</span>
              {"badge" in item && item.badge && (
                <span className="inline-flex h-4 items-center rounded-xs bg-brand-orange px-1.5 text-caption font-semibold text-white shadow-glow-orange">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border-subtle p-3">
        <div className="rounded-sm border border-border-subtle bg-bg-base p-3 shadow-inner-panel">
          <div className="flex items-center gap-2 text-caption text-text-muted">
            <div className="h-1.5 w-1.5 rounded-full bg-brand-emerald-bright shadow-glow-emerald animate-heartbeat" />
            <span>v0.1.0 prototype</span>
          </div>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-bg-surface-raised">
            <div className="h-full w-2/3 rounded-full bg-brand-emerald" />
          </div>
        </div>
      </div>
    </aside>
  );
}

function Logo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
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
