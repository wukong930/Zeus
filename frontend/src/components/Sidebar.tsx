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
    <aside className="h-full w-[220px] shrink-0 bg-bg-surface border-r border-border-subtle flex flex-col">
      <div className="flex items-center gap-2 px-5 h-14 border-b border-border-subtle select-none">
        <Logo />
        <div className="flex flex-col leading-none">
          <span className="text-h3 font-bold tracking-wider text-text-primary">ZEUS</span>
          <span className="text-caption text-text-muted">Futures Intel</span>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV_ITEMS.map((item, idx) => {
          if ("divider" in item) {
            return <div key={idx} className="h-px bg-border-subtle my-2 mx-3" />;
          }
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 px-3 h-9 rounded-sm text-sm font-medium transition-colors duration-100 relative",
                active
                  ? "bg-brand-emerald/15 text-text-primary"
                  : "text-text-secondary hover:bg-bg-surface-raised hover:text-text-primary"
              )}
            >
              {active && (
                <span className="absolute left-0 top-2 bottom-2 w-[3px] bg-brand-emerald rounded-r-sm" />
              )}
              <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
              <span className="flex-1">{item.label}</span>
              {"badge" in item && item.badge && (
                <span className="text-caption font-semibold bg-brand-orange text-white rounded-xs px-1.5 h-4 inline-flex items-center">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-border-subtle">
        <div className="flex items-center gap-2 text-caption text-text-muted">
          <div className="w-1.5 h-1.5 rounded-full bg-brand-emerald-bright shadow-glow-emerald animate-heartbeat" />
          <span>v0.1.0 prototype</span>
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
