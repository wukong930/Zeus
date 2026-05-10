"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  DatabaseZap,
  GitBranch,
  Layers3,
  Search,
  ShieldQuestion,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import {
  fetchEventImpactLinks,
  fetchEventIntelligenceItems,
  type EventImpactDirection,
  type EventImpactLink,
  type EventIntelligenceItem,
  type EventIntelligenceStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, formatPercent, timeAgo } from "@/lib/utils";

export default function EventIntelligencePage() {
  const { text } = useI18n();
  const [items, setItems] = useState<EventIntelligenceItem[]>([]);
  const [links, setLinks] = useState<EventImpactLink[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([fetchEventIntelligenceItems(200), fetchEventImpactLinks({ limit: 300 })])
      .then(([eventRows, linkRows]) => {
        if (!mounted) return;
        setItems(eventRows);
        setLinks(linkRows);
        setSource("api");
        setSelectedId(eventRows[0]?.id ?? null);
      })
      .catch(() => {
        if (!mounted) return;
        setItems([]);
        setLinks([]);
        setSource("fallback");
        setSelectedId(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => {
      return (
        item.title.toLowerCase().includes(needle) ||
        item.summary.toLowerCase().includes(needle) ||
        item.symbols.some((symbol) => symbol.toLowerCase().includes(needle)) ||
        item.mechanisms.some((mechanism) => mechanism.toLowerCase().includes(needle))
      );
    });
  }, [items, query]);

  const selected = useMemo(
    () => filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? null,
    [filtered, selectedId]
  );
  const selectedLinks = useMemo(
    () => links.filter((link) => link.eventItemId === selected?.id),
    [links, selected?.id]
  );
  const stats = useMemo(() => {
    const humanReview = items.filter((item) => item.status === "human_review").length;
    const confirmed = items.filter((item) => item.status === "confirmed").length;
    const linkedSymbols = new Set(links.map((link) => link.symbol)).size;
    return {
      events: items.length,
      links: links.length,
      humanReview,
      confirmed,
      linkedSymbols,
      maxImpact: Math.max(0, ...links.map((link) => link.impactScore)),
    };
  }, [items, links]);

  return (
    <div className="h-full overflow-y-auto px-7 py-6 animate-fade-in">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <BrainCircuit className="h-6 w-6 text-brand-emerald-bright" />
            <h1 className="text-h1 text-text-primary">{text("事件智能引擎")}</h1>
            <DataSourceBadge state={source} compact />
          </div>
          <p className="mt-1 text-sm text-text-secondary">
            {text("将新闻、天气、市场和人工事件组织成商品影响链。")}
          </p>
        </div>
        <div className="relative w-[min(360px,100%)]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={text("搜索事件 / 品种 / 机制")}
            className="h-10 w-full rounded-sm border border-border-default bg-black/42 pl-9 pr-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-brand-emerald/65 focus:shadow-focus-ring"
          />
        </div>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="事件" value={stats.events} icon={DatabaseZap} />
        <Metric label="影响链" value={stats.links} icon={GitBranch} tone="cyan" />
        <Metric label="关联品种" value={stats.linkedSymbols} icon={Layers3} tone="emerald" />
        <Metric label="人工复核" value={stats.humanReview} icon={ShieldQuestion} tone="orange" />
        <Metric label="最高影响" value={Math.round(stats.maxImpact)} icon={AlertTriangle} tone="red" />
      </div>

      <div className="grid min-h-[620px] grid-cols-[minmax(320px,0.9fr)_minmax(520px,1.4fr)] gap-5">
        <Card variant="flat" className="p-0">
          <CardHeader className="mb-0 px-4 pt-4">
            <div>
              <CardTitle>{text("事件队列")}</CardTitle>
              <CardSubtitle>
                {filtered.length} / {items.length} {text("按影响分排序")}
              </CardSubtitle>
            </div>
          </CardHeader>
          <div className="max-h-[640px] overflow-y-auto p-3">
            {filtered.map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={cn(
                  "mb-2 w-full rounded-sm border p-3 text-left transition-colors",
                  selected?.id === item.id
                    ? "border-brand-emerald/55 bg-brand-emerald/12 shadow-focus-ring"
                    : "border-border-subtle bg-black/28 hover:border-border-default hover:bg-white/[0.04]"
                )}
              >
                <div className="mb-2 flex items-center gap-2">
                  <Badge variant={statusVariant(item.status)}>{statusLabel(item.status)}</Badge>
                  <span className="text-caption text-text-muted">{timeAgo(item.eventTimestamp)}</span>
                  <span className="flex-1" />
                  <span className="font-mono text-caption text-brand-orange">{Math.round(item.impactScore)}</span>
                </div>
                <div className="truncate text-sm font-semibold text-text-primary">{text(item.title)}</div>
                <p className="mt-1 line-clamp-2 text-xs text-text-secondary">{text(item.summary)}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {item.symbols.slice(0, 5).map((symbol) => (
                    <span
                      key={symbol}
                      className="inline-flex h-5 items-center rounded-xs border border-brand-cyan/25 bg-brand-cyan/10 px-1.5 font-mono text-caption text-brand-cyan"
                    >
                      {symbol}
                    </span>
                  ))}
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="py-12 text-center text-sm text-text-secondary">
                {text(source === "fallback" ? "事件智能接口暂不可用" : "暂无事件智能结果")}
              </div>
            )}
          </div>
        </Card>

        <section className="min-w-0">
          {selected ? (
            <EventDetail item={selected} links={selectedLinks} />
          ) : (
            <Card variant="flat" className="flex min-h-[420px] items-center justify-center text-sm text-text-secondary">
              {text(source === "fallback" ? "事件智能接口暂不可用" : "请选择事件")}
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}

function EventDetail({ item, links }: { item: EventIntelligenceItem; links: EventImpactLink[] }) {
  const { text } = useI18n();

  return (
    <div className="space-y-5">
      <Card variant="flat">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant(item.status)}>{statusLabel(item.status)}</Badge>
              <Badge variant="blue">{text(item.eventType)}</Badge>
              {item.requiresManualConfirmation && (
                <Badge variant="orange">{text("需要人工确认")}</Badge>
              )}
            </div>
            <h2 className="text-h2 text-text-primary">{text(item.title)}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-text-secondary">{text(item.summary)}</p>
          </div>
          <div className="grid min-w-[220px] grid-cols-2 gap-2 text-right">
            <Score label="置信度" value={formatPercent(item.confidence * 100, 0, false)} />
            <Score label="影响" value={String(Math.round(item.impactScore))} />
            <Score label="来源可信" value={formatPercent(item.sourceReliability * 100, 0, false)} />
            <Score label="新鲜度" value={formatPercent(item.freshnessScore * 100, 0, false)} />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <TokenGroup title="品种" values={item.symbols} />
          <TokenGroup title="机制" values={item.mechanisms.map(mechanismLabel)} tone="orange" />
          <TokenGroup title="区域" values={item.regions} tone="cyan" />
        </div>
      </Card>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>{text("影响链")}</CardTitle>
            <CardSubtitle>{links.length} {text("条候选链路")}</CardSubtitle>
          </div>
        </CardHeader>
        <div className="space-y-3">
          {links.map((link) => (
            <div
              key={link.id}
              className="rounded-sm border border-border-subtle bg-black/30 p-3 shadow-inner-panel"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-semibold text-text-primary">{link.symbol}</span>
                <ArrowRight className="h-3.5 w-3.5 text-text-muted" />
                <Badge variant={directionVariant(link.direction)}>{directionLabel(link.direction)}</Badge>
                <Badge variant="neutral">{mechanismLabel(link.mechanism)}</Badge>
                <span className="ml-auto font-mono text-sm text-brand-orange">
                  {Math.round(link.impactScore)}
                </span>
              </div>
              <p className="text-sm text-text-secondary">{text(link.rationale)}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-caption text-text-muted">
                <span>{text("区域")}：{link.regionId ?? "global"}</span>
                <span>{text("周期")}：{text(link.horizon)}</span>
                <span>{text("置信度")}：{formatPercent(link.confidence * 100, 0, false)}</span>
              </div>
            </div>
          ))}
          {links.length === 0 && (
            <div className="py-10 text-center text-sm text-text-secondary">
              {text("当前事件暂无商品影响链")}
            </div>
          )}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <EvidencePanel title="证据" values={item.evidence} />
        <EvidencePanel title="反证" values={item.counterevidence} />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: number;
  icon: typeof DatabaseZap;
  tone?: "neutral" | "emerald" | "cyan" | "orange" | "red";
}) {
  const { text } = useI18n();
  const toneClass = {
    neutral: "border-border-default text-text-primary",
    emerald: "border-brand-emerald/35 text-brand-emerald-bright",
    cyan: "border-brand-cyan/35 text-brand-cyan",
    orange: "border-brand-orange/35 text-brand-orange",
    red: "border-data-down/35 text-data-down",
  }[tone];
  return (
    <div className={cn("rounded-sm border bg-black/36 p-3 shadow-inner-panel", toneClass)}>
      <div className="mb-3 flex items-center justify-between text-text-muted">
        <span className="text-caption">{text(label)}</span>
        <Icon className="h-4 w-4" />
      </div>
      <div className="font-mono text-2xl text-text-primary">{value}</div>
    </div>
  );
}

function Score({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return (
    <div className="rounded-sm border border-border-subtle bg-black/32 px-3 py-2">
      <div className="text-caption text-text-muted">{text(label)}</div>
      <div className="mt-1 font-mono text-sm text-text-primary">{value}</div>
    </div>
  );
}

function TokenGroup({
  title,
  values,
  tone = "emerald",
}: {
  title: string;
  values: string[];
  tone?: "emerald" | "orange" | "cyan";
}) {
  const { text } = useI18n();
  const toneClass = {
    emerald: "border-brand-emerald/25 bg-brand-emerald/10 text-brand-emerald-bright",
    orange: "border-brand-orange/25 bg-brand-orange/10 text-brand-orange",
    cyan: "border-brand-cyan/25 bg-brand-cyan/10 text-brand-cyan",
  }[tone];
  return (
    <div className="rounded-sm border border-border-subtle bg-black/24 p-3">
      <div className="mb-2 text-caption text-text-muted">{text(title)}</div>
      <div className="flex flex-wrap gap-1.5">
        {values.length > 0 ? (
          values.map((value) => (
            <span key={value} className={cn("rounded-xs border px-2 py-1 text-caption", toneClass)}>
              {text(value)}
            </span>
          ))
        ) : (
          <span className="text-caption text-text-muted">{text("暂无")}</span>
        )}
      </div>
    </div>
  );
}

function EvidencePanel({ title, values }: { title: string; values: string[] }) {
  const { text } = useI18n();
  return (
    <Card variant="flat">
      <CardTitle>{text(title)}</CardTitle>
      <div className="mt-3 space-y-2">
        {values.length > 0 ? (
          values.map((value, index) => (
            <div key={`${value}-${index}`} className="rounded-sm border border-border-subtle bg-black/26 p-3 text-sm text-text-secondary">
              {text(value)}
            </div>
          ))
        ) : (
          <div className="py-6 text-sm text-text-muted">{text("暂无")}</div>
        )}
      </div>
    </Card>
  );
}

function statusVariant(status: EventIntelligenceStatus): "emerald" | "orange" | "neutral" | "down" {
  if (status === "confirmed") return "emerald";
  if (status === "human_review") return "orange";
  if (status === "rejected") return "down";
  return "neutral";
}

function statusLabel(status: EventIntelligenceStatus): string {
  return {
    shadow_review: "影子复核",
    human_review: "人工复核",
    confirmed: "已确认",
    rejected: "已拒绝",
  }[status];
}

function directionVariant(direction: EventImpactDirection): "up" | "down" | "orange" | "neutral" {
  if (direction === "bullish") return "up";
  if (direction === "bearish") return "down";
  if (direction === "mixed") return "orange";
  return "neutral";
}

function directionLabel(direction: EventImpactDirection): string {
  return {
    bullish: "利多",
    bearish: "利空",
    mixed: "混合",
    watch: "观察",
  }[direction];
}

function mechanismLabel(mechanism: string): string {
  return {
    supply: "供应",
    demand: "需求",
    logistics: "物流",
    policy: "政策",
    inventory: "库存",
    cost: "成本",
    risk_sentiment: "风险情绪",
    geopolitical: "地缘",
    weather: "天气",
    macro: "宏观",
  }[mechanism] ?? mechanism;
}
