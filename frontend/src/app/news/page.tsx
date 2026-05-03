"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Newspaper,
  Radio,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { fetchNewsEventsFromApi, type NewsEvent } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

const MOCK_NEWS_EVENTS: NewsEvent[] = [
  {
    id: "news-demo-1",
    source: "cailianshe",
    rawUrl: null,
    title: "OPEC+ 宣布延长自愿减产，原油短线走强",
    summary: "OPEC+ 延长自愿减产安排，市场重新评估二季度供应缺口，对 SC 原油形成偏多冲击。",
    publishedAt: new Date(Date.now() - 22 * 60_000).toISOString(),
    eventType: "supply",
    affectedSymbols: ["SC"],
    direction: "bullish",
    severity: 5,
    timeHorizon: "medium",
    confidence: 0.82,
    sourceCount: 2,
    verificationStatus: "cross_verified",
    requiresManualConfirmation: false,
  },
  {
    id: "news-demo-2",
    source: "sina_futures",
    rawUrl: null,
    title: "泰国南部橡胶主产区连续强降雨",
    summary: "合艾和宋卡降雨持续，割胶节奏受扰，NR/RU 近端供应预期收紧。",
    publishedAt: new Date(Date.now() - 74 * 60_000).toISOString(),
    eventType: "weather",
    affectedSymbols: ["NR", "RU"],
    direction: "bullish",
    severity: 4,
    timeHorizon: "short",
    confidence: 0.74,
    sourceCount: 2,
    verificationStatus: "cross_verified",
    requiresManualConfirmation: false,
  },
  {
    id: "news-demo-3",
    source: "exchange_announcements",
    rawUrl: null,
    title: "交易所提示铁矿石合约交易风险",
    summary: "交易所发布铁矿石波动风险提示，单源高严重度事件等待人工确认后再进入评估。",
    publishedAt: new Date(Date.now() - 3 * 3600_000).toISOString(),
    eventType: "policy",
    affectedSymbols: ["I"],
    direction: "mixed",
    severity: 4,
    timeHorizon: "immediate",
    confidence: 0.68,
    sourceCount: 1,
    verificationStatus: "single_source",
    requiresManualConfirmation: true,
  },
];

const EVENT_TYPES = ["all", "policy", "supply", "demand", "inventory", "weather", "breaking"];
const DIRECTIONS = ["all", "bullish", "bearish", "mixed", "unclear"];

export default function NewsEventsPage() {
  const [events, setEvents] = useState<NewsEvent[]>([]);
  const [source, setSource] = useState<"loading" | "api" | "mock">("loading");
  const [query, setQuery] = useState("");
  const [eventType, setEventType] = useState("all");
  const [direction, setDirection] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
        if (!ignore) {
          setEvents(rows);
          setSource("api");
          setSelectedId(rows[0]?.id ?? null);
        }
      })
      .catch(() => {
        if (!ignore) {
          setEvents(MOCK_NEWS_EVENTS);
          setSource("mock");
          setSelectedId(MOCK_NEWS_EVENTS[0]?.id ?? null);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

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

  const selected = filtered.find((event) => event.id === selectedId) ?? filtered[0] ?? null;
  const stats = {
    total: events.length,
    verified: events.filter((event) => event.verificationStatus === "cross_verified").length,
    manual: events.filter((event) => event.requiresManualConfirmation).length,
  };

  return (
    <div className="flex h-full">
      <aside className="w-80 border-r border-border-subtle p-5 overflow-y-auto space-y-5">
        <div>
          <h1 className="text-h1 text-text-primary">News Events</h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-caption text-text-muted">
              {filtered.length} / {events.length}
            </p>
            <Badge variant={source === "mock" ? "orange" : "emerald"}>
              {source === "loading" ? "SYNC" : source.toUpperCase()}
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <Metric label="总数" value={stats.total} icon={Newspaper} />
          <Metric label="验证" value={stats.verified} icon={ShieldCheck} />
          <Metric label="确认" value={stats.manual} icon={AlertTriangle} />
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="品种 / 标题 / 摘要"
            className="w-full bg-bg-surface border border-border-default rounded-sm pl-9 pr-3 h-9 text-sm focus:border-brand-emerald focus:outline-none"
          />
        </div>

        <Segmented value={eventType} values={EVENT_TYPES} onChange={setEventType} />
        <Segmented value={direction} values={DIRECTIONS} onChange={setDirection} />
      </aside>

      <main className="flex-1 min-w-0 grid grid-cols-[minmax(360px,0.9fr)_minmax(420px,1.1fr)]">
        <section className="border-r border-border-subtle overflow-y-auto p-5 space-y-3">
          {filtered.map((event) => (
            <button
              key={event.id}
              onClick={() => setSelectedId(event.id)}
              className={cn(
                "w-full text-left rounded-sm border p-4 transition-colors",
                selected?.id === event.id
                  ? "bg-bg-surface-raised border-brand-emerald/70"
                  : "bg-bg-surface border-border-subtle hover:bg-bg-surface-raised"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <Badge variant={severityVariant(event.severity)}>
                  S{event.severity}
                </Badge>
                <Badge variant={directionVariant(event.direction)}>{event.direction}</Badge>
                <span className="text-caption text-text-muted font-mono">{event.source}</span>
                <span className="flex-1" />
                <span className="text-caption text-text-muted">{timeAgo(event.publishedAt)}</span>
              </div>
              <div className="text-h3 text-text-primary mb-1">{event.title}</div>
              <p className="text-sm text-text-secondary line-clamp-2">{event.summary}</p>
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
              {source === "loading" ? "新闻事件加载中" : "没有匹配的新闻事件"}
            </Card>
          )}
        </section>

        <section className="overflow-y-auto p-6">
          {selected ? <NewsEventDetail event={selected} /> : null}
        </section>
      </main>
    </div>
  );
}

function NewsEventDetail({ event }: { event: NewsEvent }) {
  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Badge variant={severityVariant(event.severity)}>Severity {event.severity}</Badge>
          <Badge variant={directionVariant(event.direction)}>{event.direction}</Badge>
          <Badge variant={event.requiresManualConfirmation ? "orange" : "emerald"}>
            {event.verificationStatus}
          </Badge>
        </div>
        <h2 className="text-h1 text-text-primary">{event.title}</h2>
        <p className="text-sm text-text-secondary mt-2 leading-relaxed">{event.summary}</p>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Info label="类型" value={event.eventType} />
        <Info label="时效" value={event.timeHorizon} />
        <Info label="来源数" value={String(event.sourceCount)} />
        <Info label="置信度" value={`${Math.round(event.confidence * 100)}%`} />
      </div>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>影响品种</CardTitle>
            <CardSubtitle>{event.publishedAt.slice(0, 19).replace("T", " ")}</CardSubtitle>
          </div>
          <Radio className="w-4 h-4 text-brand-emerald-bright" />
        </CardHeader>
        <div className="flex flex-wrap gap-2">
          {event.affectedSymbols.map((symbol) => (
            <span
              key={symbol}
              className="font-mono text-sm px-3 h-8 inline-flex items-center bg-bg-base text-text-primary rounded-sm border border-border-default"
            >
              {symbol}
            </span>
          ))}
        </div>
      </Card>

      <Card variant="flat">
        <CardHeader>
          <div>
            <CardTitle>质量门槛</CardTitle>
            <CardSubtitle>source quorum / severity gate / manual gate</CardSubtitle>
          </div>
          {event.requiresManualConfirmation ? (
            <AlertTriangle className="w-4 h-4 text-brand-orange" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-brand-emerald-bright" />
          )}
        </CardHeader>
        <div className="grid grid-cols-3 gap-3">
          <Gate active={event.severity >= 3} label="严重度 ≥ 3" />
          <Gate active={event.sourceCount >= 2} label="跨源验证" />
          <Gate active={!event.requiresManualConfirmation} label="无需确认" />
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
          原文链接
        </a>
      )}
    </div>
  );
}

function Metric({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Newspaper }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-sm p-3">
      <Icon className="w-4 h-4 text-text-muted mb-2" />
      <div className="text-h2 font-mono text-text-primary">{value}</div>
      <div className="text-caption text-text-muted">{label}</div>
    </div>
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
  return (
    <div className="grid grid-cols-2 gap-1">
      {values.map((item) => (
        <button
          key={item}
          onClick={() => onChange(item)}
          className={cn(
            "h-8 rounded-sm text-xs font-medium border transition-colors capitalize",
            value === item
              ? "bg-brand-emerald/15 border-brand-emerald text-brand-emerald-bright"
              : "border-border-subtle text-text-secondary hover:bg-bg-surface-raised"
          )}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-sm p-3 min-w-0">
      <div className="text-caption text-text-muted mb-1">{label}</div>
      <div className="text-sm text-text-primary truncate">{value}</div>
    </div>
  );
}

function Gate({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 bg-bg-base border border-border-subtle rounded-sm px-3 h-9">
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

function directionVariant(direction: NewsEvent["direction"]): "up" | "down" | "orange" | "neutral" {
  if (direction === "bullish") return "up";
  if (direction === "bearish") return "down";
  if (direction === "mixed") return "orange";
  return "neutral";
}
