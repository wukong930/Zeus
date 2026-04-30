"use client";

import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import {
  Search,
  LayoutDashboard,
  Bell,
  Plane,
  Network,
  Factory,
  Layers,
  Beaker,
  NotebookPen,
  BarChart3,
  Sparkles,
  Plus,
  TrendingUp,
} from "lucide-react";
import { SECTORS } from "@/data/mock";

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  icon: React.ComponentType<{ className?: string }>;
  group: string;
  action: () => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const close = () => setOpen(false);
  const go = (path: string) => {
    router.push(path);
    close();
  };

  const items: CommandItem[] = [
    { id: "nav-cc", group: "跳转", label: "Command Center", icon: LayoutDashboard, action: () => go("/") },
    { id: "nav-al", group: "跳转", label: "Alerts", icon: Bell, action: () => go("/alerts") },
    { id: "nav-tp", group: "跳转", label: "Trade Plans", icon: Plane, action: () => go("/trade-plans") },
    { id: "nav-cw", group: "跳转", label: "Causal Web", icon: Network, action: () => go("/causal-web") },
    { id: "nav-il", group: "跳转", label: "Industry Lens", icon: Factory, action: () => go("/industry") },
    { id: "nav-sec", group: "跳转", label: "Sectors", icon: Layers, action: () => go("/sectors") },
    { id: "nav-fl", group: "跳转", label: "Future Lab", icon: Beaker, action: () => go("/future-lab") },
    { id: "nav-nb", group: "跳转", label: "Notebook", icon: NotebookPen, action: () => go("/notebook") },
    { id: "nav-an", group: "跳转", label: "Analytics", icon: BarChart3, action: () => go("/analytics") },
    ...SECTORS.flatMap((sec) =>
      sec.symbols.map((sym) => ({
        id: `sym-${sym.code}`,
        group: "品种",
        label: `${sym.code}  ${sym.name}`,
        icon: TrendingUp,
        action: () => go("/causal-web"),
      }))
    ),
    { id: "act-pos", group: "操作", label: "添加持仓", icon: Plus, action: () => go("/portfolio") },
    { id: "act-ai", group: "操作", label: "询问 AI Companion", icon: Sparkles, action: close },
    { id: "act-note", group: "操作", label: "创建笔记", icon: NotebookPen, action: () => go("/notebook") },
  ];

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100]">
      <div
        className="absolute inset-0 bg-black/70 animate-fade-in"
        onClick={close}
      />
      <div className="relative max-w-2xl mx-auto mt-[10vh] mx-4 animate-fade-in">
        <Command
          label="Command Palette"
          className="bg-bg-surface-overlay border border-border-default rounded-md shadow-lg overflow-hidden"
        >
          <div className="flex items-center gap-3 px-4 h-12 border-b border-border-default">
            <Search className="w-4 h-4 text-text-muted shrink-0" />
            <Command.Input
              placeholder="搜索品种 / 跳转 / 执行..."
              className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted text-sm focus:outline-none"
            />
            <kbd className="text-caption text-text-muted bg-bg-surface px-1.5 py-0.5 rounded-xs border border-border-default">
              ESC
            </kbd>
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-text-muted">
              没找到匹配项
            </Command.Empty>
            {["跳转", "品种", "操作"].map((g) => (
              <Command.Group key={g} heading={g} className="text-caption text-text-muted uppercase tracking-wider px-2 py-2">
                {items
                  .filter((i) => i.group === g)
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <Command.Item
                        key={item.id}
                        onSelect={item.action}
                        className="flex items-center gap-3 px-3 h-9 rounded-sm cursor-pointer text-sm text-text-secondary aria-selected:bg-brand-emerald/15 aria-selected:text-text-primary"
                      >
                        <Icon className="w-4 h-4 shrink-0" />
                        <span>{item.label}</span>
                      </Command.Item>
                    );
                  })}
              </Command.Group>
            ))}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
