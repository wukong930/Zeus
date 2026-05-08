"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  Globe2,
} from "lucide-react";
import { fetchContracts, type ContractMetadata } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  icon: React.ComponentType<{ className?: string }>;
  group: string;
  action: () => void;
  disabled?: boolean;
}

type ContractsState = "loading" | "api" | "fallback";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [contracts, setContracts] = useState<ContractMetadata[]>([]);
  const [contractsState, setContractsState] = useState<ContractsState>("loading");
  const router = useRouter();
  const { text } = useI18n();

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

  const close = useCallback(() => setOpen(false), []);
  const go = useCallback((path: string) => {
    router.push(path);
    close();
  }, [close, router]);

  useEffect(() => {
    let mounted = true;
    fetchContracts()
      .then((rows) => {
        if (!mounted) return;
        setContracts(rows);
        setContractsState("api");
      })
      .catch(() => {
        if (!mounted) return;
        setContracts([]);
        setContractsState("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const symbolItems = useMemo(
    () => buildContractCommandItems(contracts, go, text),
    [contracts, go, text]
  );
  const symbolStatusItem = useMemo<CommandItem | null>(() => {
    if (contractsState === "loading") {
      return {
        id: "sym-loading",
        group: "品种",
        label: "合约同步中",
        icon: TrendingUp,
        action: () => undefined,
        disabled: true,
      };
    }
    if (contractsState === "fallback") {
      return {
        id: "sym-fallback",
        group: "品种",
        label: "合约接口暂不可用",
        icon: TrendingUp,
        action: () => undefined,
        disabled: true,
      };
    }
    if (symbolItems.length === 0) {
      return {
        id: "sym-empty",
        group: "品种",
        label: "暂无合约数据",
        icon: TrendingUp,
        action: () => undefined,
        disabled: true,
      };
    }
    return null;
  }, [contractsState, symbolItems.length]);

  const items: CommandItem[] = useMemo(
    () => [
      { id: "nav-cc", group: "跳转", label: "命令中心", icon: LayoutDashboard, action: () => go("/") },
      { id: "nav-al", group: "跳转", label: "预警", icon: Bell, action: () => go("/alerts") },
      { id: "nav-tp", group: "跳转", label: "交易计划", icon: Plane, action: () => go("/trade-plans") },
      { id: "nav-cw", group: "跳转", label: "因果网络", icon: Network, action: () => go("/causal-web") },
      { id: "nav-wm", group: "跳转", label: "世界风险地图", icon: Globe2, action: () => go("/world-map") },
      { id: "nav-il", group: "跳转", label: "产业透镜", icon: Factory, action: () => go("/industry") },
      { id: "nav-sec", group: "跳转", label: "板块", icon: Layers, action: () => go("/sectors") },
      { id: "nav-fl", group: "跳转", label: "未来实验室", icon: Beaker, action: () => go("/future-lab") },
      { id: "nav-nb", group: "跳转", label: "笔记本", icon: NotebookPen, action: () => go("/notebook") },
      { id: "nav-an", group: "跳转", label: "分析", icon: BarChart3, action: () => go("/analytics") },
      ...(symbolStatusItem ? [symbolStatusItem] : symbolItems),
      { id: "act-pos", group: "操作", label: "添加持仓", icon: Plus, action: () => go("/portfolio") },
      { id: "act-ai", group: "操作", label: "询问 AI Companion", icon: Sparkles, action: close },
      { id: "act-note", group: "操作", label: "创建笔记", icon: NotebookPen, action: () => go("/notebook") },
    ],
    [close, go, symbolItems, symbolStatusItem]
  );
  const itemsByGroup = useMemo(() => {
    const grouped = new Map<string, CommandItem[]>();
    for (const item of items) {
      const bucket = grouped.get(item.group);
      if (bucket) {
        bucket.push(item);
      } else {
        grouped.set(item.group, [item]);
      }
    }
    return grouped;
  }, [items]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100]">
      <div
        className="absolute inset-0 bg-black/78 backdrop-blur-sm animate-fade-in"
        onClick={close}
      />
      <div className="relative mx-auto mt-[10vh] w-[min(720px,calc(100vw-32px))] animate-fade-in">
        <Command
          label="Command Palette"
          className="overflow-hidden rounded-md border border-border-default bg-[linear-gradient(180deg,rgba(31,31,31,0.98),rgba(5,7,6,0.98))] shadow-data-panel"
        >
          <div className="flex h-14 items-center gap-3 border-b border-border-default px-4">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-brand-emerald/30 bg-brand-emerald/10 text-brand-emerald-bright">
              <Search className="h-4 w-4" />
            </div>
            <Command.Input
              placeholder={text("搜索品种 / 跳转 / 执行...")}
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
            />
            <kbd className="rounded-xs border border-border-default bg-bg-base px-1.5 py-0.5 text-caption text-text-muted shadow-inner-panel">
              ESC
            </kbd>
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-3">
            <Command.Empty className="py-8 text-center text-sm text-text-muted">
              {text("没找到匹配项")}
            </Command.Empty>
            {["跳转", "品种", "操作"].map((g) => (
              <Command.Group key={g} heading={text(g)} className="px-1 py-2 text-caption uppercase tracking-wider text-text-muted">
                {(itemsByGroup.get(g) ?? [])
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <Command.Item
                        key={item.id}
                        onSelect={item.action}
                        disabled={item.disabled}
                        className="flex h-10 cursor-pointer items-center gap-3 rounded-sm border border-transparent px-3 text-sm text-text-secondary transition-colors aria-disabled:cursor-not-allowed aria-disabled:opacity-45 aria-selected:border-brand-emerald/35 aria-selected:bg-brand-emerald/12 aria-selected:text-text-primary"
                      >
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-xs border border-border-subtle bg-bg-base text-text-muted">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <span className="flex-1">{text(item.label)}</span>
                        {item.shortcut && (
                          <kbd className="rounded-xs border border-border-subtle bg-bg-base px-1.5 py-0.5 text-caption text-text-muted">
                            {item.shortcut}
                          </kbd>
                        )}
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

function buildContractCommandItems(
  contracts: ContractMetadata[],
  go: (path: string) => void,
  text: (source: string) => string
): CommandItem[] {
  const bySymbol = new Map<string, ContractMetadata>();
  for (const contract of contracts) {
    const current = bySymbol.get(contract.symbol);
    if (!current || contractRank(contract) > contractRank(current)) {
      bySymbol.set(contract.symbol, contract);
    }
  }
  return [...bySymbol.values()]
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
    .map((contract) => ({
      id: `sym-${contract.symbol}`,
      group: "品种",
      label: contractLabel(contract, text),
      shortcut: contract.is_main ? text("主力") : undefined,
      icon: TrendingUp,
      action: () => go(`/causal-web?symbol=${encodeURIComponent(contract.symbol)}`),
    }));
}

function contractRank(contract: ContractMetadata): number {
  return (contract.is_main ? 1_000_000_000 : 0) + (contract.volume ?? 0) + (contract.open_interest ?? 0) / 100;
}

function contractLabel(contract: ContractMetadata, text: (source: string) => string): string {
  const name = contract.commodity ? text(contract.commodity) : contract.exchange ?? contract.contract_month;
  return `${contract.symbol}  ${name}`;
}
