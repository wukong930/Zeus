"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  ExternalLink,
  GitBranch,
  Loader2,
  Newspaper,
  Radio,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import { MetricTile } from "@/components/MetricTile";
import {
  createEventIntelligenceFromNews,
  fetchEventImpactLinks,
  fetchEventIntelligenceItems,
  fetchNewsEventsFromApi,
  type EventImpactLink,
  type EventIntelligenceItem,
  type NewsEvent,
} from "@/lib/api";
import { cn, formatPercent, timeAgo } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export default function NewsEventsPage() {
  const [events, setEvents] = useState<NewsEvent[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [query, setQuery] = useState("");
  const [eventType, setEventType] = useState("all");
  const [direction, setDirection] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [intelligenceByNewsId, setIntelligenceByNewsId] = useState<Map<string, EventIntelligenceItem>>(
    new Map()
  );
  const [impactLinksByEventId, setImpactLinksByEventId] = useState<Map<string, EventImpactLink[]>>(
    new Map()
  );
  const [intelligenceSource, setIntelligenceSource] = useState<DataSourceState>("loading");
  const [intelligencePendingId, setIntelligencePendingId] = useState<string | null>(null);
  const [intelligenceError, setIntelligenceError] = useState<string | null>(null);

  useEffect(() => {
    const initialSymbol = new URLSearchParams(window.location.search)
      .get("symbol")
      ?.replace(/\d+/g, "")
      .toUpperCase();
    if (initialSymbol) {
      setQuery(initialSymbol);
    }

    let ignore = false;
    fetchNewsEventsFromApi()
      .then((rows) => {
        if (ignore) return;
        setEvents(rows);
        setSource("api");
        setSelectedId(rows[0]?.id ?? null);
      })
      .catch(() => {
        if (ignore) return;
        setEvents([]);
        setSource("fallback");
        setSelectedId(null);
      });

    Promise.all([fetchEventIntelligenceItems(300), fetchEventImpactLinks({ limit: 500 })])
      .then(([items, links]) => {
        if (ignore) return;
        setIntelligenceByNewsId(groupEventIntelligenceByNewsId(items));
        setImpactLinksByEventId(groupImpactLinksByEventId(links));
        setIntelligenceSource("api");
      })
      .catch(() => {
        if (ignore) return;
        setIntelligenceByNewsId(new Map());
        setImpactLinksByEventId(new Map());
        setIntelligenceSource("fallback");
      });
    return () => {
      ignore = true;
    };
  }, []);

  const eventTypeOptions = useMemo(
    () => buildFilterValues(events.map((event) => event.eventType)),
    [events]
  );
  const directionOptions = useMemo(
    () => buildFilterValues(events.map((event) => event.direction)),
    [events]
  );

  useEffect(() => {
    if (!eventTypeOptions.includes(eventType)) setEventType("all");
  }, [eventType, eventTypeOptions]);

  useEffect(() => {
    if (!directionOptions.includes(direction)) setDirection("all");
  }, [direction, directionOptions]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      const matchesQuery =
        !needle ||
        event.title.toLowerCase().includes(needle) ||
        event.summary.toLowerCase().includes(needle) ||
        event.affectedSymbols.some((symbol) => symbol.toLowerCase().includes(needle));
      const matchesType = eventType === "all" || event.eventType === eventType;
      const matchesDirection = direction === "all" || event.direction === direction;
      return matchesQuery && matchesType && matchesDirection;
    });
  }, [direction, eventType, events, query]);

  const selected = useMemo(
    () => filtered.find((event) => event.id === selectedId) ?? filtered[0] ?? null,
    [filtered, selectedId]
  );
  const selectedIntelligence = selected
    ? intelligenceByNewsId.get(selected.id) ?? null
    : null;
  const selectedImpactLinks = selectedIntelligence
    ? impactLinksByEventId.get(selectedIntelligence.id) ?? []
    : [];
  const stats = useMemo(() => {
    let verified = 0;
    let manual = 0;
    for (const event of events) {
      if (event.verificationStatus === "cross_verified") verified += 1;
      if (event.requiresManualConfirmation) manual += 1;
    }
    return {
      manual,
      total: events.length,
      verified,
    };
  }, [events]);
  const { text } = useI18n();

  const handleGenerateEventIntelligence = async (event: NewsEvent) => {
    setIntelligencePendingId(event.id);
    setIntelligenceError(null);
    try {
      const result = await createEventIntelligenceFromNews(event.id);
      setIntelligenceByNewsId((current) => {
        const next = new Map(current);
        next.set(event.id, result.event);
        if (result.event.sourceId) next.set(result.event.sourceId, result.event);
        return next;
      });
      setImpactLinksByEventId((current) => {
        const next = new Map(current);
        next.set(result.event.id, result.impactLinks);
        return next;
      });
      setIntelligenceSource("api");
    } catch (error) {
      setIntelligenceError(
        error instanceof Error ? error.message : text("事件智能生成失败")
      );
    } finally {
      setIntelligencePendingId(null);
    }
  };

  return (
    <div className="flex h-full">
      <aside className="w-80 border-r border-border-subtle p-5 overflow-y-auto space-y-5">
        <div>
          <h1 className="text-h1 text-text-primary">{text("News Events")}</h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-caption text-text-muted">
              {filtered.length} / {events.length}
            </p>
            <DataSourceBadge state={source} compact />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3">
          <MetricTile
            label={text("总数")}
            value={String(stats.total)}
            caption={text("events")}
            icon={Newspaper}
            tone="cyan"
          />
          <MetricTile
            label={text("交叉验证")}
            value={String(stats.verified)}
            caption={text("source quorum")}
            icon={ShieldCheck}
            tone="up"
          />
          <MetricTile
            label={text("人工确认")}
            value={String(stats.manual)}
            caption={text("manual gate")}
            icon={AlertTriangle}
            tone={stats.manual > 0 ? "warning" : "neutral"}
          />
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={text("品种 / 标题 / 摘要")}
            className="w-full rounded-sm border border-border-default bg-bg-base pl-9 pr-3 h-9 text-sm focus:border-brand-emerald focus:outline-none focus:shadow-focus-ring"
          />
        </div>

        <Segmented value={eventType} values={eventTypeOptions} onChange={setEventType} />
        <Segmented value={direction} values={directionOptions} onChange={setDirection} />
      </aside>

      <main className="flex-1 min-w-0 grid grid-cols-[minmax(360px,0.9fr)_minmax(420px,1.1fr)]">
        <section className="border-r border-border-subtle overflow-y-auto p-5 space-y-3">
          {filtered.map((event) => (
            <button
              type="button"
              key={event.id}
              onClick={() => setSelectedId(event.id)}
              className={cn(
                "w-full text-left rounded-sm border p-4 transition-colors",
                selected?.id === event.id
                  ? "border-brand-emerald/70 bg-brand-emerald/10 shadow-focus-ring"
                  : "border-border-subtle bg-bg-surface hover:border-border-default hover:bg-bg-surface-raised"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <Badge variant={severityVariant(event.severity)}>
                  S{event.severity}
                </Badge>
                <Badge variant={directionVariant(event.direction)}>{text(event.direction)}</Badge>
                <span className="text-caption text-text-muted font-mono">{event.source}</span>
                {intelligenceByNewsId.get(event.id) && (
                  <Badge variant="cyan">
                    <GitBranch className="h-3 w-3" />
                    {text("事件链")}
                  </Badge>
                )}
                <span className="flex-1" />
                <span className="text-caption text-text-muted">{timeAgo(event.publishedAt)}</span>
              </div>
              <div className="text-h3 text-text-primary mb-1">{text(event.title)}</div>
              <p className="text-sm text-text-secondary line-clamp-2">{text(event.summary)}</p>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {event.affectedSymbols.map((symbol) => (
                  <span
                    key={symbol}
                    className="font-mono text-caption px-1.5 h-5 inline-flex items-center bg-bg-base text-text-secondary rounded-xs border border-border-subtle"
                  >
                    {symbol}
                  </span>
                ))}
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <Card variant="flat" className="py-10 text-center text-text-muted">
              {text(emptyNewsMessage(source, events.length, query, eventType, direction))}
            </Card>
          )}
        </section>

        <section className="overflow-y-auto p-6">
          {selected ? (
            <NewsEventDetail
              event={selected}
              intelligence={selectedIntelligence}
              impactLinks={selectedImpactLinks}
              intelligenceSource={intelligenceSource}
              isGenerating={intelligencePendingId === selected.id}
              intelligenceError={intelligenceError}
              onGenerate={handleGenerateEventIntelligence}
            />
          ) : (
            <Card variant="flat" className="py-12 text-center text-sm text-text-secondary">
              {text(source === "fallback" ? "新闻事件接口暂不可用" : "请选择新闻事件")}
            </Card>
          )}
        </section>
      </main>
    </div>
  );
}

function emptyNewsMessage(
  source: DataSourceState,
  totalEvents: number,
  query: string,
  eventType: string,
  direction: string
): string {
  if (source === "loading") return "新闻事件加载中";
  if (source === "fallback") return "新闻事件接口暂不可用";
  if (totalEvents === 0) return "当前暂无新闻事件";
  if (query.trim() || eventType !== "all" || direction !== "all") return "没有匹配的新闻事件";
  return "当前暂无新闻事件";
}

function buildFilterValues(values: string[]): string[] {
  const counts = new Map<string, number>();
  for (const value of values) {
    if (value.trim()) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [
    "all",
    ...Array.from(counts.entries())
      .sort(([leftValue, leftCount], [rightValue, rightCount]) => {
        if (leftCount !== rightCount) return rightCount - leftCount;
        return leftValue.localeCompare(rightValue);
      })
      .map(([value]) => value),
  ];
}

function groupEventIntelligenceByNewsId(items: EventIntelligenceItem[]) {
  const byNewsId = new Map<string, EventIntelligenceItem>();
  for (const item of items) {
    if (item.sourceType !== "news_event" || !item.sourceId) continue;
    const current = byNewsId.get(item.sourceId);
    if (!current || item.impactScore > current.impactScore) {
      byNewsId.set(item.sourceId, item);
    }
  }
  return byNewsId;
}

function groupImpactLinksByEventId(links: EventImpactLink[]) {
  const byEventId = new Map<string, EventImpactLink[]>();
  for (const link of links) {
    const current = byEventId.get(link.eventItemId) ?? [];
    current.push(link);
    byEventId.set(link.eventItemId, current);
  }
  for (const [eventId, eventLinks] of byEventId) {
    byEventId.set(
      eventId,
      [...eventLinks].sort((left, right) => right.impactScore - left.impactScore)
    );
  }
  return byEventId;
}

function NewsEventDetail({
  event,
  intelligence,
  impactLinks,
  intelligenceSource,
  isGenerating,
  intelligenceError,
  onGenerate,
}: {
  event: NewsEvent;
  intelligence: EventIntelligenceItem | null;
  impactLinks: EventImpactLink[];
  intelligenceSource: DataSourceState;
  isGenerating: boolean;
  intelligenceError: string | null;
  onGenerate: (event: NewsEvent) => void;
}) {
  const { text } = useI18n();

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Badge variant={severityVariant(event.severity)}>
            {text("Severity")} {event.severity}
          </Badge>
          <Badge variant={directionVariant(event.direction)}>{text(event.direction)}</Badge>
          <Badge variant={event.requiresManualConfirmation ? "orange" : "emerald"}>
            {event.verificationStatus}
          </Badge>
        </div>
        <h2 className="text-h1 text-text-primary">{text(event.title)}</h2>
        <p className="text-sm text-text-secondary mt-2 leading-relaxed">{text(event.summary)}</p>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Info label={text("类型")} value={text(event.eventType)} />
        <Info label={text("时效")} value={text(event.timeHorizon)} />
        <Info label={text("来源数")} value={String(event.sourceCount)} />
        <Info label={text("置信度")} value={`${Math.round(event.confidence * 100)}%`} />
      </div>

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>{text("影响品种")}</CardTitle>
            <CardSubtitle>{event.publishedAt.slice(0, 19).replace("T", " ")}</CardSubtitle>
          </div>
          <Radio className="w-4 h-4 text-brand-emerald-bright" />
        </CardHeader>
        <div className="flex flex-wrap gap-2">
          {event.affectedSymbols.map((symbol) => (
            <span
              key={symbol}
              className="font-mono text-sm px-3 h-8 inline-flex items-center bg-bg-base text-text-primary rounded-sm border border-border-default shadow-inner-panel"
            >
              {symbol}
            </span>
          ))}
        </div>
      </Card>

      <EventIntelligencePanel
        event={event}
        intelligence={intelligence}
        impactLinks={impactLinks}
        source={intelligenceSource}
        isGenerating={isGenerating}
        error={intelligenceError}
        onGenerate={onGenerate}
      />

      <Card variant="data">
        <CardHeader>
          <div>
            <CardTitle>{text("质量门槛")}</CardTitle>
            <CardSubtitle>{text("来源共识 / 严重度门槛 / 人工门槛")}</CardSubtitle>
          </div>
          {event.requiresManualConfirmation ? (
            <AlertTriangle className="w-4 h-4 text-brand-orange" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-brand-emerald-bright" />
          )}
        </CardHeader>
        <div className="grid grid-cols-3 gap-3">
          <Gate active={event.severity >= 3} label={text("严重度 ≥ 3")} />
          <Gate active={event.sourceCount >= 2} label={text("跨源验证")} />
          <Gate active={!event.requiresManualConfirmation} label={text("无需确认")} />
        </div>
      </Card>

      {event.rawUrl && (
        <a
          href={event.rawUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-sm text-brand-emerald-bright hover:text-brand-emerald"
        >
          <ExternalLink className="w-4 h-4" />
          {text("原文链接")}
        </a>
      )}
    </div>
  );
}

function EventIntelligencePanel({
  event,
  intelligence,
  impactLinks,
  source,
  isGenerating,
  error,
  onGenerate,
}: {
  event: NewsEvent;
  intelligence: EventIntelligenceItem | null;
  impactLinks: EventImpactLink[];
  source: DataSourceState;
  isGenerating: boolean;
  error: string | null;
  onGenerate: (event: NewsEvent) => void;
}) {
  const { text } = useI18n();

  return (
    <Card variant="data" className="border-brand-cyan/25">
      <CardHeader>
        <div>
          <CardTitle>{text("事件智能链")}</CardTitle>
          <CardSubtitle>{text("从新闻生成可审计的商品影响链")}</CardSubtitle>
        </div>
        {intelligence ? (
          <Badge variant={eventIntelligenceStatusVariant(intelligence.status)}>
            {text(eventIntelligenceStatusLabel(intelligence.status))}
          </Badge>
        ) : (
          <DataSourceBadge state={source} compact />
        )}
      </CardHeader>

      {intelligence ? (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <Info label={text("影响分")} value={String(Math.round(intelligence.impactScore))} />
            <Info
              label={text("置信度")}
              value={formatPercent(intelligence.confidence * 100, 0, false)}
            />
            <Info label={text("影响链")} value={String(impactLinks.length)} />
            <Info label={text("更新时间")} value={timeAgo(intelligence.updatedAt)} />
          </div>

          <div className="space-y-2">
            {impactLinks.slice(0, 3).map((link) => (
              <div
                key={link.id}
                className="flex items-center gap-3 rounded-sm border border-border-subtle bg-bg-base px-3 py-2 text-sm shadow-inner-panel"
              >
                <Badge variant={directionVariant(link.direction)}>
                  {text(link.direction)}
                </Badge>
                <span className="font-mono text-text-primary">{link.symbol}</span>
                <span className="min-w-0 flex-1 truncate text-text-secondary">
                  {text(link.mechanism)} · {text(link.horizon)}
                </span>
                <span className="font-mono text-text-muted">
                  {Math.round(link.impactScore)}
                </span>
              </div>
            ))}
            {impactLinks.length === 0 && (
              <div className="rounded-sm border border-border-subtle bg-bg-base px-3 py-4 text-sm text-text-muted">
                {text("当前事件暂无影响链明细")}
              </div>
            )}
          </div>

          <Link
            href={`/event-intelligence?event=${encodeURIComponent(intelligence.id)}`}
            className="inline-flex h-9 items-center gap-2 rounded-sm border border-brand-cyan/35 bg-brand-cyan/10 px-3 text-sm text-brand-cyan transition-colors hover:bg-brand-cyan/16"
          >
            <GitBranch className="h-4 w-4" />
            {text("查看事件智能链")}
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-sm border border-border-subtle bg-bg-base p-4 text-sm text-text-secondary shadow-inner-panel">
            {text("当前新闻尚未生成事件智能链，可一键解析人物、地区、商品和影响机制。")}
          </div>
          {error && (
            <div className="rounded-sm border border-data-down/35 bg-data-down/10 p-3 text-sm text-data-down">
              {text("事件智能生成失败")}：{error}
            </div>
          )}
          <button
            type="button"
            disabled={isGenerating || source === "loading"}
            onClick={() => onGenerate(event)}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-brand-emerald/35 bg-brand-emerald/15 px-4 text-sm font-medium text-brand-emerald-bright transition-colors hover:bg-brand-emerald/22 disabled:cursor-not-allowed disabled:opacity-55"
          >
            {isGenerating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <BrainCircuit className="h-4 w-4" />
            )}
            {text(isGenerating ? "生成中" : "生成事件智能链")}
          </button>
        </div>
      )}
    </Card>
  );
}

function Segmented({
  value,
  values,
  onChange,
}: {
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  const { text } = useI18n();

  return (
    <div className="grid grid-cols-2 gap-1">
      {values.map((item) => (
        <button
          type="button"
          key={item}
          onClick={() => onChange(item)}
          className={cn(
            "h-8 rounded-sm text-xs font-medium border transition-colors capitalize",
            value === item
              ? "bg-brand-emerald/15 border-brand-emerald text-brand-emerald-bright"
              : "border-border-subtle text-text-secondary hover:bg-bg-surface-raised"
          )}
        >
          {text(item)}
        </button>
      ))}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-sm p-3 min-w-0 shadow-inner-panel">
      <div className="text-caption text-text-muted mb-1">{label}</div>
      <div className="text-sm text-text-primary truncate">{value}</div>
    </div>
  );
}

function Gate({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 bg-bg-base border border-border-subtle rounded-sm px-3 h-9 shadow-inner-panel">
      <span className={cn("w-2 h-2 rounded-full", active ? "bg-brand-emerald" : "bg-brand-orange")} />
      <span className="text-sm text-text-secondary">{label}</span>
    </div>
  );
}

function severityVariant(severity: number): "critical" | "high" | "medium" | "low" {
  if (severity >= 5) return "critical";
  if (severity >= 4) return "high";
  if (severity >= 3) return "medium";
  return "low";
}

function directionVariant(
  direction: NewsEvent["direction"] | EventImpactLink["direction"]
): "up" | "down" | "orange" | "neutral" {
  if (direction === "bullish") return "up";
  if (direction === "bearish") return "down";
  if (direction === "mixed") return "orange";
  return "neutral";
}

function eventIntelligenceStatusVariant(
  status: EventIntelligenceItem["status"]
): "emerald" | "orange" | "neutral" | "down" {
  if (status === "confirmed") return "emerald";
  if (status === "human_review") return "orange";
  if (status === "rejected") return "down";
  return "neutral";
}

function eventIntelligenceStatusLabel(status: EventIntelligenceItem["status"]) {
  return {
    shadow_review: "影子复核",
    human_review: "人工复核",
    confirmed: "已确认",
    rejected: "已拒绝",
  }[status];
}
