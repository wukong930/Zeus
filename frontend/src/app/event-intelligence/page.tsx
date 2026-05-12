"use client";

import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  Gauge,
  GitBranch,
  Layers3,
  Pencil,
  Save,
  Search,
  ShieldQuestion,
  X,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import {
  decideEventIntelligence,
  fetchEventImpactLinks,
  fetchEventIntelligenceAuditLogs,
  fetchEventIntelligenceDetail,
  fetchEventIntelligenceItems,
  fetchEventIntelligenceQualitySummary,
  updateEventImpactLink,
  type EventIntelligenceDecision,
  type EventImpactDirection,
  type EventImpactLink,
  type EventImpactLinkUpdateInput,
  type EventIntelligenceAuditLog,
  type EventIntelligenceItem,
  type EventIntelligenceQualityReport,
  type EventIntelligenceQualityStatus,
  type EventImpactLinkQuality,
  type EventImpactLinkQualityStatus,
  type EventIntelligenceStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  readWorldMapNavigationScope,
  type WorldMapNavigationScope,
} from "@/lib/navigation-scope";
import { cn, formatPercent, timeAgo } from "@/lib/utils";

interface SemanticHypothesisPayload {
  symbol: string;
  regionId: string | null;
  mechanism: string;
  direction: EventImpactDirection;
  confidence: number;
  horizon: string;
  rationale: string;
}

const IMPACT_DIRECTION_OPTIONS: EventImpactDirection[] = ["bullish", "bearish", "mixed", "watch"];
const IMPACT_MECHANISM_OPTIONS = [
  "supply",
  "demand",
  "logistics",
  "policy",
  "inventory",
  "cost",
  "risk_sentiment",
  "geopolitical",
  "weather",
  "macro",
];
const IMPACT_EDIT_INPUT_CLASS =
  "w-full rounded-sm border border-border-subtle bg-black/42 px-2.5 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-brand-cyan/55 focus:shadow-focus-ring";

export default function EventIntelligencePage() {
  const { text } = useI18n();
  const [items, setItems] = useState<EventIntelligenceItem[]>([]);
  const [links, setLinks] = useState<EventImpactLink[]>([]);
  const [qualityReports, setQualityReports] = useState<EventIntelligenceQualityReport[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [decisionPending, setDecisionPending] = useState<EventIntelligenceDecision | null>(null);
  const [linkEditPendingId, setLinkEditPendingId] = useState<string | null>(null);
  const [linkEditError, setLinkEditError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<EventIntelligenceAuditLog[]>([]);
  const [auditSource, setAuditSource] = useState<DataSourceState>("loading");
  const [navigationScope, setNavigationScope] = useState<WorldMapNavigationScope | null>(null);

  useEffect(() => {
    let mounted = true;
    const initialParams = new URLSearchParams(window.location.search);
    const initialEventId = initialParams.get("event");
    const initialScope = readWorldMapNavigationScope(initialParams);
    if (initialScope) {
      setNavigationScope(initialScope);
      if (initialScope.symbol) setQuery(initialScope.symbol);
    }
    Promise.all([
      fetchEventIntelligenceItems(200),
      fetchEventImpactLinks({ limit: 300 }),
      fetchEventIntelligenceQualitySummary(200),
    ])
      .then(async ([eventRows, linkRows, qualitySummary]) => {
        if (!mounted) return;
        let nextItems = eventRows;
        let nextLinks = linkRows;
        let nextSelectedId =
          initialEventId && eventRows.some((item) => item.id === initialEventId)
            ? initialEventId
            : eventRows[0]?.id ?? null;
        if (initialEventId && !eventRows.some((item) => item.id === initialEventId)) {
          try {
            const detail = await fetchEventIntelligenceDetail(initialEventId);
            nextItems = [detail.event, ...eventRows];
            nextLinks = [
              ...detail.impactLinks,
              ...linkRows.filter((link) => link.eventItemId !== detail.event.id),
            ];
            nextSelectedId = detail.event.id;
          } catch {
            nextSelectedId = eventRows[0]?.id ?? null;
          }
        }
        if (!mounted) return;
        setItems(nextItems);
        setLinks(nextLinks);
        setQualityReports(qualitySummary.reports);
        setSource("api");
        setSelectedId(nextSelectedId);
      })
      .catch(() => {
        if (!mounted) return;
        setItems([]);
        setLinks([]);
        setQualityReports([]);
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
  const qualityByEventId = useMemo(
    () => new Map(qualityReports.map((report) => [report.eventId, report])),
    [qualityReports]
  );
  const selectedQuality = selected ? qualityByEventId.get(selected.id) ?? null : null;

  useEffect(() => {
    if (!selected?.id) {
      setAuditLogs([]);
      setAuditSource(source === "fallback" ? "fallback" : "loading");
      return;
    }
    let mounted = true;
    setAuditSource("loading");
    fetchEventIntelligenceAuditLogs({ eventItemId: selected.id, limit: 20 })
      .then((rows) => {
        if (!mounted) return;
        setAuditLogs(rows);
        setAuditSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setAuditLogs([]);
        setAuditSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, [selected?.id, source]);

  const stats = useMemo(() => {
    const humanReview = items.filter((item) => item.status === "human_review").length;
    const confirmed = items.filter((item) => item.status === "confirmed").length;
    const linkedSymbols = new Set(links.map((link) => link.symbol)).size;
    const passedQuality = qualityReports.filter((report) => report.passedGate).length;
    return {
      events: items.length,
      links: links.length,
      humanReview,
      confirmed,
      linkedSymbols,
      passedQuality,
      maxImpact: Math.max(0, ...links.map((link) => link.impactScore)),
    };
  }, [items, links, qualityReports]);

  const handleDecision = async (decision: EventIntelligenceDecision) => {
    if (!selected) return;
    setDecisionPending(decision);
    try {
      const result = await decideEventIntelligence(selected.id, decision, decisionNote(decision));
      setItems((current) =>
        current.map((item) => (item.id === result.event.id ? result.event : item))
      );
      setLinks((current) =>
        current.map((link) =>
          link.eventItemId === result.event.id
            ? { ...link, status: result.event.status }
            : link
        )
      );
      setAuditLogs((current) => mergeAuditLogs([result.auditLog, ...current]));
      setAuditSource("api");
    } finally {
      setDecisionPending(null);
    }
  };

  const handleUpdateImpactLink = async (
    linkId: string,
    payload: EventImpactLinkUpdateInput
  ): Promise<boolean> => {
    setLinkEditPendingId(linkId);
    setLinkEditError(null);
    try {
      const result = await updateEventImpactLink(linkId, payload);
      setItems((current) =>
        current.map((item) => (item.id === result.event.id ? result.event : item))
      );
      setLinks((current) =>
        current.map((link) =>
          link.id === result.impactLink.id ? result.impactLink : link
        )
      );
      const qualitySummary = await fetchEventIntelligenceQualitySummary(200).catch(() => null);
      if (qualitySummary) {
        setQualityReports(qualitySummary.reports);
      }
      setAuditLogs((current) => mergeAuditLogs([result.auditLog, ...current]));
      setAuditSource("api");
      return true;
    } catch (error) {
      setLinkEditError(error instanceof Error ? error.message : "影响链修改失败");
      return false;
    } finally {
      setLinkEditPendingId(null);
    }
  };

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

      {navigationScope && (
        <WorldMapScopeBanner
          scope={navigationScope}
          onClear={() => {
            setNavigationScope(null);
            if (
              navigationScope.symbol &&
              query.trim().toUpperCase() === navigationScope.symbol.toUpperCase()
            ) {
              setQuery("");
            }
          }}
        />
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Metric label="事件" value={stats.events} icon={DatabaseZap} />
        <Metric label="影响链" value={stats.links} icon={GitBranch} tone="cyan" />
        <Metric label="关联品种" value={stats.linkedSymbols} icon={Layers3} tone="emerald" />
        <Metric label="人工复核" value={stats.humanReview} icon={ShieldQuestion} tone="orange" />
        <Metric label="质量通过" value={stats.passedQuality} icon={Gauge} tone="emerald" />
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
              <EventQueueItem
                key={item.id}
                item={item}
                selected={selected?.id === item.id}
                quality={qualityByEventId.get(item.id) ?? null}
                onSelect={() => setSelectedId(item.id)}
              />
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
            <EventDetail
              item={selected}
              links={selectedLinks}
              quality={selectedQuality}
              onDecision={handleDecision}
              decisionPending={decisionPending}
              onUpdateImpactLink={handleUpdateImpactLink}
              linkEditPendingId={linkEditPendingId}
              linkEditError={linkEditError}
              auditLogs={auditLogs}
              auditSource={auditSource}
            />
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

function WorldMapScopeBanner({
  scope,
  onClear,
}: {
  scope: WorldMapNavigationScope;
  onClear: () => void;
}) {
  const { text } = useI18n();

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2 rounded-sm border border-brand-cyan/25 bg-brand-cyan/10 px-3 py-2 text-sm text-text-secondary shadow-inner-panel">
      <GitBranch className="h-4 w-4 text-brand-cyan" />
      <span className="font-semibold text-text-primary">{text("来自世界风险地图")}</span>
      <span>{text("已按品种过滤事件智能结果")}</span>
      {scope.symbol && (
        <span className="rounded-xs border border-brand-cyan/25 bg-black/28 px-2 py-0.5 font-mono text-caption text-brand-cyan">
          {scope.symbol}
        </span>
      )}
      {scope.region && (
        <span className="rounded-xs border border-white/[0.12] bg-black/28 px-2 py-0.5 font-mono text-caption text-text-muted">
          {scope.region}
        </span>
      )}
      <button
        type="button"
        onClick={onClear}
        className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-xs border border-border-subtle bg-black/28 px-2 text-caption text-text-secondary transition-colors hover:border-brand-cyan/35 hover:text-text-primary"
      >
        <X className="h-3.5 w-3.5" />
        {text("清除作用域")}
      </button>
    </div>
  );
}

function EventQueueItem({
  item,
  selected,
  quality,
  onSelect,
}: {
  item: EventIntelligenceItem;
  selected: boolean;
  quality: EventIntelligenceQualityReport | null;
  onSelect: () => void;
}) {
  const { text } = useI18n();

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "mb-2 w-full rounded-sm border p-3 text-left transition-colors",
        selected
          ? "border-brand-emerald/55 bg-brand-emerald/12 shadow-focus-ring"
          : "border-border-subtle bg-black/28 hover:border-border-default hover:bg-white/[0.04]"
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <Badge variant={statusVariant(item.status)}>{text(statusLabel(item.status))}</Badge>
        {quality && (
          <Badge variant={qualityVariant(quality.status)}>
            {text(qualityLabel(quality.status))}
          </Badge>
        )}
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
  );
}

function EventDetail({
  item,
  links,
  quality,
  onDecision,
  decisionPending,
  onUpdateImpactLink,
  linkEditPendingId,
  linkEditError,
  auditLogs,
  auditSource,
}: {
  item: EventIntelligenceItem;
  links: EventImpactLink[];
  quality: EventIntelligenceQualityReport | null;
  onDecision: (decision: EventIntelligenceDecision) => void;
  decisionPending: EventIntelligenceDecision | null;
  onUpdateImpactLink: (linkId: string, payload: EventImpactLinkUpdateInput) => Promise<boolean>;
  linkEditPendingId: string | null;
  linkEditError: string | null;
  auditLogs: EventIntelligenceAuditLog[];
  auditSource: DataSourceState;
}) {
  const { text } = useI18n();
  const [editingLinkId, setEditingLinkId] = useState<string | null>(null);
  const semanticHypotheses = readSemanticHypotheses(item.sourcePayload);
  const semanticModel = readPayloadString(item.sourcePayload, "semantic_model");
  const semanticPrompt = readPayloadString(item.sourcePayload, "semantic_prompt_version");

  useEffect(() => {
    setEditingLinkId(null);
  }, [item.id]);

  return (
    <div className="space-y-5">
      <Card variant="flat">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant(item.status)}>{text(statusLabel(item.status))}</Badge>
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
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-sm border border-border-subtle bg-black/24 p-2">
          <DecisionButton
            label="确认"
            icon={CheckCircle2}
            decision="confirm"
            tone="emerald"
            pending={decisionPending}
            onDecision={onDecision}
          />
          <DecisionButton
            label="转人工复核"
            icon={ShieldQuestion}
            decision="request_review"
            tone="orange"
            pending={decisionPending}
            onDecision={onDecision}
          />
          <DecisionButton
            label="拒绝"
            icon={XCircle}
            decision="reject"
            tone="red"
            pending={decisionPending}
            onDecision={onDecision}
          />
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <TokenGroup title="品种" values={item.symbols} />
          <TokenGroup title="机制" values={item.mechanisms.map(mechanismLabel)} tone="orange" />
          <TokenGroup title="区域" values={item.regions} tone="cyan" />
        </div>
      </Card>

      {quality && <QualityGatePanel quality={quality} links={links} />}

      {semanticHypotheses.length > 0 && (
        <Card variant="flat">
          <CardHeader>
            <div>
              <CardTitle>{text("语义假设")}</CardTitle>
              <CardSubtitle>
                {semanticHypotheses.length} {text("条 LLM 候选影响")}
                {semanticModel ? ` · ${semanticModel}` : ""}
                {semanticPrompt ? ` · ${semanticPrompt}` : ""}
              </CardSubtitle>
            </div>
          </CardHeader>
          <div className="grid gap-3 lg:grid-cols-2">
            {semanticHypotheses.slice(0, 6).map((hypothesis, index) => (
              <div
                key={`${hypothesis.symbol}-${hypothesis.mechanism}-${index}`}
                className="rounded-sm border border-brand-emerald/18 bg-brand-emerald/8 p-3 shadow-inner-panel"
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-text-primary">
                    {hypothesis.symbol}
                  </span>
                  <Badge variant={directionVariant(hypothesis.direction)}>
                    {text(directionLabel(hypothesis.direction))}
                  </Badge>
                  <Badge variant="neutral">{text(mechanismLabel(hypothesis.mechanism))}</Badge>
                  <span className="ml-auto font-mono text-caption text-brand-emerald-bright">
                    {formatPercent(hypothesis.confidence * 100, 0, false)}
                  </span>
                </div>
                <p className="line-clamp-2 text-sm text-text-secondary">
                  {text(hypothesis.rationale || "等待语义假设说明")}
                </p>
                <div className="mt-2 flex flex-wrap gap-2 text-caption text-text-muted">
                  <span>{text("区域")}：{hypothesis.regionId ?? "global"}</span>
                  <span>{text("周期")}：{text(hypothesis.horizon)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

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
                <Badge variant={directionVariant(link.direction)}>{text(directionLabel(link.direction))}</Badge>
                <Badge variant="neutral">{text(mechanismLabel(link.mechanism))}</Badge>
                <span className="ml-auto font-mono text-sm text-brand-orange">
                  {Math.round(link.impactScore)}
                </span>
              </div>
              <p className="text-sm text-text-secondary">{text(link.rationale)}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-caption text-text-muted">
                <span>{text("区域")}：{link.regionId ?? "global"}</span>
                <span>{text("周期")}：{text(link.horizon)}</span>
                <span>{text("置信度")}：{formatPercent(link.confidence * 100, 0, false)}</span>
                <button
                  type="button"
                  disabled={linkEditPendingId !== null}
                  onClick={() =>
                    setEditingLinkId((current) => (current === link.id ? null : link.id))
                  }
                  className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-sm border border-brand-cyan/30 bg-brand-cyan/10 px-2 text-caption text-brand-cyan transition-colors hover:bg-brand-cyan/16 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {text("修改链路")}
                </button>
              </div>
              {editingLinkId === link.id && (
                <ImpactLinkEditForm
                  link={link}
                  pending={linkEditPendingId === link.id}
                  error={linkEditError}
                  onCancel={() => setEditingLinkId(null)}
                  onSubmit={async (payload) => {
                    const ok = await onUpdateImpactLink(link.id, payload);
                    if (ok) setEditingLinkId(null);
                  }}
                />
              )}
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

      <AuditTimeline logs={auditLogs} source={auditSource} />
    </div>
  );
}

function AuditTimeline({
  logs,
  source,
}: {
  logs: EventIntelligenceAuditLog[];
  source: DataSourceState;
}) {
  const { text } = useI18n();

  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>{text("治理时间线")}</CardTitle>
          <CardSubtitle>{text("确认、复核、语义增强和影响链修改留痕")}</CardSubtitle>
        </div>
        <DataSourceBadge state={source} compact />
      </CardHeader>
      <div className="space-y-3">
        {logs.map((log) => (
          <div
            key={log.id}
            className="rounded-sm border border-border-subtle bg-black/28 p-3 shadow-inner-panel"
          >
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-sm border border-brand-cyan/25 bg-brand-cyan/10 text-brand-cyan">
                <Clock3 className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-text-primary">
                  {text(auditActionLabel(log.action))}
                </div>
                <div className="mt-0.5 text-caption text-text-muted">
                  {timeAgo(log.createdAt)}
                  {log.actor ? ` · ${text("操作者")} ${log.actor}` : ""}
                </div>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                {log.beforeStatus && (
                  <Badge variant={statusVariant(log.beforeStatus as EventIntelligenceStatus)}>
                    {text(statusLabel(log.beforeStatus as EventIntelligenceStatus))}
                  </Badge>
                )}
                {(log.beforeStatus || log.afterStatus) && (
                  <ArrowRight className="h-3.5 w-3.5 text-text-muted" />
                )}
                {log.afterStatus && (
                  <Badge variant={statusVariant(log.afterStatus as EventIntelligenceStatus)}>
                    {text(statusLabel(log.afterStatus as EventIntelligenceStatus))}
                  </Badge>
                )}
              </div>
            </div>
            {log.note && (
              <p className="mb-2 rounded-xs border border-border-subtle bg-black/24 px-2 py-1.5 text-xs text-text-secondary">
                {text(log.note)}
              </p>
            )}
            <AuditPayloadSummary log={log} />
          </div>
        ))}
        {source === "loading" && (
          <div className="py-6 text-center text-sm text-text-secondary">
            {text("正在加载治理历史")}
          </div>
        )}
        {source !== "loading" && logs.length === 0 && (
          <div className="py-6 text-center text-sm text-text-secondary">
            {text(source === "fallback" ? "治理历史暂不可用" : "暂无治理历史")}
          </div>
        )}
      </div>
    </Card>
  );
}

function AuditPayloadSummary({ log }: { log: EventIntelligenceAuditLog }) {
  const { text } = useI18n();
  const changedFields = stringListPayload(log.payload.changed_fields);
  const reviewReasons = stringListPayload(log.payload.review_reasons);
  const semanticHypothesesCount =
    numberPayload(log.payload.hypothesis_count) ??
    numberPayload(log.payload.semantic_hypotheses_count);
  const productionEffect = stringPayload(log.payload.production_effect);

  if (
    changedFields.length === 0 &&
    reviewReasons.length === 0 &&
    semanticHypothesesCount === null &&
    !productionEffect
  ) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-1.5 text-caption">
      {changedFields.map((field) => (
        <span
          key={`field-${field}`}
          className="rounded-xs border border-brand-cyan/25 bg-brand-cyan/10 px-1.5 py-0.5 text-brand-cyan"
        >
          {text("字段")} {text(auditFieldLabel(field))}
        </span>
      ))}
      {reviewReasons.map((reason) => (
        <span
          key={`reason-${reason}`}
          className="rounded-xs border border-brand-orange/25 bg-brand-orange/10 px-1.5 py-0.5 text-brand-orange"
        >
          {text(auditReasonLabel(reason))}
        </span>
      ))}
      {semanticHypothesesCount !== null && (
        <span className="rounded-xs border border-brand-emerald/25 bg-brand-emerald/10 px-1.5 py-0.5 text-brand-emerald-bright">
          {semanticHypothesesCount} {text("条语义假设")}
        </span>
      )}
      {productionEffect && (
        <span className="rounded-xs border border-border-subtle bg-white/[0.03] px-1.5 py-0.5 text-text-muted">
          {text("生产影响")}：{text(auditProductionEffectLabel(productionEffect))}
        </span>
      )}
    </div>
  );
}

function ImpactLinkEditForm({
  link,
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  link: EventImpactLink;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (payload: EventImpactLinkUpdateInput) => Promise<void>;
}) {
  const { text } = useI18n();
  const [symbol, setSymbol] = useState(link.symbol);
  const [regionId, setRegionId] = useState(link.regionId ?? "");
  const [mechanism, setMechanism] = useState(link.mechanism);
  const [direction, setDirection] = useState<EventImpactDirection>(link.direction);
  const [confidence, setConfidence] = useState(String(Math.round(link.confidence * 100)));
  const [impactScore, setImpactScore] = useState(String(Math.round(link.impactScore)));
  const [horizon, setHorizon] = useState(link.horizon);
  const [rationale, setRationale] = useState(link.rationale);
  const [evidence, setEvidence] = useState(link.evidence.join("\n"));
  const [counterevidence, setCounterevidence] = useState(link.counterevidence.join("\n"));
  const [note, setNote] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    if (!symbol.trim() || !horizon.trim() || !rationale.trim()) {
      setLocalError("品种、周期和机制说明不能为空");
      return;
    }
    const payload = buildImpactLinkPatch(link, {
      symbol,
      regionId,
      mechanism,
      direction,
      confidence,
      impactScore,
      horizon,
      rationale,
      evidence,
      counterevidence,
      note,
    });
    if (Object.keys(payload).filter((key) => key !== "note").length === 0) {
      setLocalError("没有可保存的链路修改");
      return;
    }
    await onSubmit(payload);
  };

  return (
    <form
      onSubmit={submit}
      className="mt-3 rounded-sm border border-brand-cyan/22 bg-brand-cyan/8 p-3"
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-text-primary">{text("人工修改影响链")}</div>
          <p className="mt-1 text-caption text-text-muted">
            {text("修改后回到人工复核，不改变生产阈值。")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-border-default bg-black/24 px-2.5 text-caption text-text-secondary transition-colors hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            {text("取消")}
          </button>
          <button
            type="submit"
            disabled={pending}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-brand-emerald/35 bg-brand-emerald/12 px-2.5 text-caption text-brand-emerald-bright transition-colors hover:bg-brand-emerald/18 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" />
            {text(pending ? "保存中" : "保存修改")}
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <ImpactEditField label="品种">
          <input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "font-mono uppercase")}
          />
        </ImpactEditField>
        <ImpactEditField label="区域">
          <input
            value={regionId}
            onChange={(event) => setRegionId(event.target.value)}
            placeholder="global"
            className={IMPACT_EDIT_INPUT_CLASS}
          />
        </ImpactEditField>
        <ImpactEditField label="机制">
          <select
            value={mechanism}
            onChange={(event) => setMechanism(event.target.value)}
            className={IMPACT_EDIT_INPUT_CLASS}
          >
            {IMPACT_MECHANISM_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {text(mechanismLabel(option))}
              </option>
            ))}
          </select>
        </ImpactEditField>
        <ImpactEditField label="方向">
          <select
            value={direction}
            onChange={(event) => setDirection(event.target.value as EventImpactDirection)}
            className={IMPACT_EDIT_INPUT_CLASS}
          >
            {IMPACT_DIRECTION_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {text(directionLabel(option))}
              </option>
            ))}
          </select>
        </ImpactEditField>
        <ImpactEditField label="置信度">
          <input
            type="number"
            min="0"
            max="100"
            step="1"
            value={confidence}
            onChange={(event) => setConfidence(event.target.value)}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "font-mono")}
          />
        </ImpactEditField>
        <ImpactEditField label="影响分">
          <input
            type="number"
            min="0"
            max="100"
            step="1"
            value={impactScore}
            onChange={(event) => setImpactScore(event.target.value)}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "font-mono")}
          />
        </ImpactEditField>
        <ImpactEditField label="周期">
          <input
            value={horizon}
            onChange={(event) => setHorizon(event.target.value)}
            className={IMPACT_EDIT_INPUT_CLASS}
          />
        </ImpactEditField>
        <ImpactEditField label="编辑备注">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={text("说明本次修改原因")}
            className={IMPACT_EDIT_INPUT_CLASS}
          />
        </ImpactEditField>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <ImpactEditField label="机制说明">
          <textarea
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            rows={4}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "min-h-[96px] resize-y leading-5")}
          />
        </ImpactEditField>
        <ImpactEditField label="支持证据">
          <textarea
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            placeholder={text("每行一条证据")}
            rows={4}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "min-h-[96px] resize-y leading-5")}
          />
        </ImpactEditField>
        <ImpactEditField label="反证线索">
          <textarea
            value={counterevidence}
            onChange={(event) => setCounterevidence(event.target.value)}
            placeholder={text("每行一条反证")}
            rows={4}
            className={cn(IMPACT_EDIT_INPUT_CLASS, "min-h-[96px] resize-y leading-5")}
          />
        </ImpactEditField>
      </div>

      {(localError || error) && (
        <div className="mt-3 rounded-sm border border-data-down/25 bg-data-down/10 p-2 text-caption text-data-down">
          {text(localError ?? error ?? "影响链修改失败")}
        </div>
      )}
    </form>
  );
}

function ImpactEditField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const { text } = useI18n();
  return (
    <label className="block">
      <span className="mb-1 block text-caption text-text-muted">{text(label)}</span>
      {children}
    </label>
  );
}

function QualityGatePanel({
  quality,
  links,
}: {
  quality: EventIntelligenceQualityReport;
  links: EventImpactLink[];
}) {
  const { text } = useI18n();
  const linkById = useMemo(() => new Map(links.map((link) => [link.id, link])), [links]);

  return (
    <Card variant="flat">
      <CardHeader>
        <div>
          <CardTitle>{text("质量门槛")}</CardTitle>
          <CardSubtitle>{text("证据、来源、作用域和影响链完整性")}</CardSubtitle>
        </div>
        <Badge variant={qualityVariant(quality.status)}>{text(qualityLabel(quality.status))}</Badge>
      </CardHeader>
      <div className="grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)]">
        <div className="rounded-sm border border-border-subtle bg-black/30 p-3">
          <div className="text-caption text-text-muted">{text("质量评分")}</div>
          <div className="mt-2 font-mono text-4xl text-text-primary">{quality.score}</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border-subtle">
            <div
              className={cn(
                "h-full rounded-full",
                quality.status === "blocked"
                  ? "bg-data-down"
                  : quality.status === "review"
                    ? "bg-brand-orange"
                    : "bg-brand-emerald"
              )}
              style={{ width: `${quality.score}%` }}
            />
          </div>
        </div>
        <div className="min-w-0">
          <IssueList issues={quality.issues} />
          <div className="mt-3 grid gap-2 xl:grid-cols-2">
            {quality.linkReports.slice(0, 6).map((report) => (
              <LinkQualityRow
                key={report.id}
                report={report}
                link={linkById.get(report.id) ?? null}
              />
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function IssueList({ issues }: { issues: EventIntelligenceQualityReport["issues"] }) {
  const { text } = useI18n();
  if (issues.length === 0) {
    return (
      <div className="rounded-sm border border-brand-emerald/20 bg-brand-emerald/8 p-3 text-sm text-brand-emerald-bright">
        {text("当前事件通过质量门，暂无阻断项。")}
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      {issues.slice(0, 5).map((issue) => (
        <div
          key={`${issue.code}-${issue.severity}`}
          className={cn(
            "rounded-sm border p-2 text-sm",
            issue.severity === "blocker"
              ? "border-data-down/25 bg-data-down/10 text-data-down"
              : issue.severity === "warning"
                ? "border-brand-orange/25 bg-brand-orange/10 text-brand-orange"
                : "border-border-subtle bg-black/22 text-text-secondary"
          )}
        >
          <span className="mr-2 font-mono text-caption">{text(issue.severity)}</span>
          {text(issue.message)}
        </div>
      ))}
    </div>
  );
}

function LinkQualityRow({
  report,
  link,
}: {
  report: EventImpactLinkQuality;
  link: EventImpactLink | null;
}) {
  const { text } = useI18n();

  return (
    <div className="rounded-sm border border-border-subtle bg-black/22 p-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm text-text-primary">{report.symbol}</span>
        <Badge variant={linkQualityVariant(report.status)}>{text(linkQualityLabel(report.status))}</Badge>
        <span className="ml-auto font-mono text-sm text-text-primary">{report.score}</span>
      </div>
      <div className="mt-1 text-caption text-text-muted">
        {text(mechanismLabel(report.mechanism))}
        {link?.regionId ? ` · ${link.regionId}` : ""}
      </div>
      {report.issues.length > 0 && (
        <div className="mt-2 line-clamp-1 text-caption text-text-secondary">
          {text(report.issues[0].message)}
        </div>
      )}
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

function DecisionButton({
  label,
  icon: Icon,
  decision,
  tone,
  pending,
  onDecision,
}: {
  label: string;
  icon: typeof CheckCircle2;
  decision: EventIntelligenceDecision;
  tone: "emerald" | "orange" | "red";
  pending: EventIntelligenceDecision | null;
  onDecision: (decision: EventIntelligenceDecision) => void;
}) {
  const { text } = useI18n();
  const toneClass = {
    emerald: "border-brand-emerald/35 text-brand-emerald-bright hover:bg-brand-emerald/12",
    orange: "border-brand-orange/35 text-brand-orange hover:bg-brand-orange/12",
    red: "border-data-down/35 text-data-down hover:bg-data-down/12",
  }[tone];
  const isPending = pending === decision;
  return (
    <button
      type="button"
      disabled={pending !== null}
      onClick={() => onDecision(decision)}
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-sm border bg-black/28 px-3 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        toneClass
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{text(isPending ? "处理中" : label)}</span>
    </button>
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

function qualityVariant(status: EventIntelligenceQualityStatus): "emerald" | "orange" | "neutral" | "down" {
  if (status === "decision_grade" || status === "shadow_ready") return "emerald";
  if (status === "review") return "orange";
  return "down";
}

function qualityLabel(status: EventIntelligenceQualityStatus): string {
  return {
    blocked: "质量阻断",
    review: "质量复核",
    shadow_ready: "影子可用",
    decision_grade: "决策级",
  }[status];
}

function linkQualityVariant(status: EventImpactLinkQualityStatus): "emerald" | "orange" | "down" {
  if (status === "passed") return "emerald";
  if (status === "review") return "orange";
  return "down";
}

function linkQualityLabel(status: EventImpactLinkQualityStatus): string {
  return {
    blocked: "阻断",
    review: "复核",
    passed: "已通过",
  }[status];
}

function auditActionLabel(action: string): string {
  return {
    resolved: "规则解析生成",
    semantic_enhanced: "语义增强",
    "review.queued": "进入治理队列",
    "decision.confirm": "确认通过",
    "decision.reject": "人工拒绝",
    "decision.request_review": "转人工复核",
    "decision.shadow_review": "回到影子复核",
    "impact_link.updated": "影响链修改",
  }[action] ?? action;
}

function auditFieldLabel(field: string): string {
  return {
    symbol: "品种",
    region_id: "区域",
    mechanism: "机制",
    direction: "方向",
    confidence: "置信度",
    impact_score: "影响分",
    horizon: "周期",
    rationale: "机制说明",
    evidence: "支持证据",
    counterevidence: "反证线索",
  }[field] ?? field;
}

function auditReasonLabel(reason: string): string {
  return {
    manual_confirmation_required: "需要人工确认",
    single_source: "单一来源",
    low_confidence: "低置信",
    low_source_reliability: "低来源可信度",
    high_impact_uncertain_event: "高影响不确定事件",
    impact_link_requires_review: "影响链需要复核",
  }[reason] ?? reason;
}

function auditProductionEffectLabel(effect: string): string {
  return {
    none: "无生产影响",
  }[effect] ?? effect;
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

interface ImpactLinkDraft {
  symbol: string;
  regionId: string;
  mechanism: string;
  direction: EventImpactDirection;
  confidence: string;
  impactScore: string;
  horizon: string;
  rationale: string;
  evidence: string;
  counterevidence: string;
  note: string;
}

function buildImpactLinkPatch(
  link: EventImpactLink,
  draft: ImpactLinkDraft
): EventImpactLinkUpdateInput {
  const payload: EventImpactLinkUpdateInput = {};
  const nextSymbol = draft.symbol.trim().toUpperCase();
  const nextRegionId = draft.regionId.trim() || null;
  const nextConfidence = clampNumber(
    numericDraftValue(draft.confidence, link.confidence * 100),
    0,
    100
  ) / 100;
  const nextImpactScore = clampNumber(
    numericDraftValue(draft.impactScore, link.impactScore),
    0,
    100
  );
  const nextHorizon = draft.horizon.trim();
  const nextRationale = draft.rationale.trim();
  const nextEvidence = splitLines(draft.evidence);
  const nextCounterevidence = splitLines(draft.counterevidence);
  const nextNote = draft.note.trim();

  if (nextSymbol !== link.symbol) payload.symbol = nextSymbol;
  if (nextRegionId !== link.regionId) payload.regionId = nextRegionId;
  if (draft.mechanism !== link.mechanism) payload.mechanism = draft.mechanism;
  if (draft.direction !== link.direction) payload.direction = draft.direction;
  if (!nearlyEqual(nextConfidence, link.confidence, 0.0001)) payload.confidence = nextConfidence;
  if (!nearlyEqual(nextImpactScore, link.impactScore, 0.01)) payload.impactScore = nextImpactScore;
  if (nextHorizon !== link.horizon) payload.horizon = nextHorizon;
  if (nextRationale !== link.rationale) payload.rationale = nextRationale;
  if (!sameStringList(nextEvidence, link.evidence)) payload.evidence = nextEvidence;
  if (!sameStringList(nextCounterevidence, link.counterevidence)) {
    payload.counterevidence = nextCounterevidence;
  }
  if (nextNote) payload.note = nextNote;
  return payload;
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function numericDraftValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function nearlyEqual(left: number, right: number, tolerance: number): boolean {
  return Math.abs(left - right) <= tolerance;
}

function sameStringList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((item, index) => item === right[index]);
}

function mergeAuditLogs(logs: EventIntelligenceAuditLog[]): EventIntelligenceAuditLog[] {
  const byId = new Map<string, EventIntelligenceAuditLog>();
  for (const log of logs) {
    byId.set(log.id, log);
  }
  return Array.from(byId.values())
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
    .slice(0, 20);
}

function stringPayload(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberPayload(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringListPayload(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function readPayloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function readSemanticHypotheses(payload: Record<string, unknown>): SemanticHypothesisPayload[] {
  const raw = payload.semantic_hypotheses;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const symbol = stringValue(record.symbol);
    const mechanism = stringValue(record.mechanism);
    const direction = directionValue(record.direction);
    if (!symbol || !mechanism || !direction) return [];
    return [
      {
        symbol,
        regionId: stringValue(record.region_id),
        mechanism,
        direction,
        confidence: numberValue(record.confidence),
        horizon: stringValue(record.horizon) ?? "short",
        rationale: stringValue(record.rationale) ?? "",
      },
    ];
  });
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function directionValue(value: unknown): EventImpactDirection | null {
  if (value === "bullish" || value === "bearish" || value === "mixed" || value === "watch") {
    return value;
  }
  return null;
}

function decisionNote(decision: EventIntelligenceDecision): string {
  return {
    confirm: "UI operator confirmed this event intelligence result.",
    reject: "UI operator rejected this event intelligence result.",
    request_review: "UI operator requested manual review for this event intelligence result.",
    shadow_review: "UI operator returned this event intelligence result to shadow review.",
  }[decision];
}
