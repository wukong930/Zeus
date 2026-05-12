"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  Eye,
  Layers3,
  Search,
  ShieldCheck,
  ShieldQuestion,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, CardSubtitle, CardTitle } from "@/components/Card";
import { DataSourceBadge, type DataSourceState } from "@/components/DataSourceBadge";
import {
  decideGovernanceReview,
  fetchGovernanceReviews,
  type GovernanceReview,
  type GovernanceReviewDecision,
  type GovernanceReviewStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn, timeAgo } from "@/lib/utils";

type StatusFilter = "all" | GovernanceReviewStatus;

interface ImpactLinkSummary {
  symbol: string;
  mechanism: string;
  direction: string;
  impactScore: number | null;
  status: string | null;
}

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "pending", label: "待复核" },
  { id: "approved", label: "已批准" },
  { id: "rejected", label: "已驳回" },
  { id: "reviewed", label: "已审查" },
  { id: "shadow_review", label: "影子复核" },
];

const ACTIONS: {
  decision: GovernanceReviewDecision;
  label: string;
  icon: typeof CheckCircle2;
  variant: "primary" | "secondary" | "destructive" | "ghost";
}[] = [
  { decision: "approve", label: "批准", icon: CheckCircle2, variant: "primary" },
  { decision: "reject", label: "驳回", icon: XCircle, variant: "destructive" },
  { decision: "shadow_review", label: "转影子复核", icon: ShieldQuestion, variant: "secondary" },
  { decision: "mark_reviewed", label: "标记已审查", icon: Eye, variant: "ghost" },
];

export default function GovernancePage() {
  const { text } = useI18n();
  const [reviews, setReviews] = useState<GovernanceReview[]>([]);
  const [source, setSource] = useState<DataSourceState>("loading");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [decisionPending, setDecisionPending] = useState<GovernanceReviewDecision | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchGovernanceReviews({ limit: 300 })
      .then((rows) => {
        if (!mounted) return;
        setReviews(rows);
        setSelectedId(rows.find((row) => row.status === "pending")?.id ?? rows[0]?.id ?? null);
        setSource("api");
      })
      .catch(() => {
        if (!mounted) return;
        setReviews([]);
        setSelectedId(null);
        setSource("fallback");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const stats = useMemo(() => {
    const counts = new Map<string, number>();
    const sources = new Set<string>();
    for (const review of reviews) {
      counts.set(review.status, (counts.get(review.status) ?? 0) + 1);
      sources.add(review.source);
    }
    return {
      total: reviews.length,
      pending: counts.get("pending") ?? 0,
      approved: counts.get("approved") ?? 0,
      rejected: counts.get("rejected") ?? 0,
      reviewed: (counts.get("reviewed") ?? 0) + (counts.get("shadow_review") ?? 0),
      sources: sources.size,
    };
  }, [reviews]);

  const filteredReviews = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return reviews.filter((review) => {
      if (statusFilter !== "all" && review.status !== statusFilter) return false;
      if (!needle) return true;
      return (
        review.source.toLowerCase().includes(needle) ||
        review.targetTable.toLowerCase().includes(needle) ||
        review.targetKey.toLowerCase().includes(needle) ||
        reviewTitle(review).toLowerCase().includes(needle) ||
        (review.reason ?? "").toLowerCase().includes(needle) ||
        JSON.stringify(review.proposedChange).toLowerCase().includes(needle)
      );
    });
  }, [query, reviews, statusFilter]);

  const selected = useMemo(
    () => filteredReviews.find((review) => review.id === selectedId) ?? filteredReviews[0] ?? null,
    [filteredReviews, selectedId]
  );

  const handleDecision = async (decision: GovernanceReviewDecision) => {
    if (!selected) return;
    setDecisionPending(decision);
    try {
      const updated = await decideGovernanceReview(
        selected.id,
        decision,
        defaultDecisionNote(decision)
      );
      setReviews((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setSelectedId(updated.id);
      setSource("api");
    } catch {
      setSource("fallback");
    } finally {
      setDecisionPending(null);
    }
  };

  return (
    <div className="space-y-5 px-8 py-6 animate-fade-in">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-sm border border-brand-emerald/35 bg-brand-emerald/12 text-brand-emerald-bright shadow-glow-emerald">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div>
              <h1 className="text-h1 text-text-primary">{text("治理队列")}</h1>
              <p className="mt-1 text-sm text-text-secondary">
                {text("统一审核自动学习、事件智能和校准变更。")}
              </p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DataSourceBadge state={source} />
          <div className="flex h-9 items-center gap-2 rounded-sm border border-border-default bg-black/42 px-3 text-sm text-text-secondary">
            <Clock3 className="h-4 w-4 text-brand-emerald-bright" />
            <span>{text("待复核")}</span>
            <span className="font-mono text-text-primary">{stats.pending}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <GovernanceStat label="全部" value={stats.total} tone="cyan" />
        <GovernanceStat label="待复核" value={stats.pending} tone="orange" />
        <GovernanceStat label="已批准" value={stats.approved} tone="emerald" />
        <GovernanceStat label="已驳回" value={stats.rejected} tone="red" />
        <GovernanceStat label="已处理" value={stats.reviewed} tone="blue" />
        <GovernanceStat label="来源" value={stats.sources} tone="neutral" />
      </div>

      <div className="grid min-h-[calc(100vh-260px)] grid-cols-1 gap-5 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.5fr)]">
        <Card variant="data" className="p-0">
          <CardHeader className="m-0 p-4">
            <div>
              <CardTitle>{text("复核队列")}</CardTitle>
              <CardSubtitle>{text("按状态、来源和目标筛选待审建议")}</CardSubtitle>
            </div>
            <Badge variant={stats.pending ? "orange" : "emerald"}>{`${stats.pending} ${text("待复核")}`}</Badge>
          </CardHeader>

          <div className="space-y-3 border-b border-border-subtle p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={text("搜索来源 / 目标 / 变更内容")}
                className="h-10 w-full rounded-sm border border-border-subtle bg-black/45 pl-9 pr-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-brand-cyan/55 focus:shadow-focus-ring"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.id}
                  onClick={() => setStatusFilter(filter.id)}
                  className={cn(
                    "h-8 rounded-sm border px-3 text-xs font-medium transition-colors",
                    statusFilter === filter.id
                      ? "border-brand-emerald/45 bg-brand-emerald/16 text-text-primary"
                      : "border-border-subtle bg-black/28 text-text-secondary hover:border-border-strong hover:text-text-primary"
                  )}
                >
                  {text(filter.label)}
                </button>
              ))}
            </div>
          </div>

          <div className="max-h-[calc(100vh-430px)] min-h-[360px] overflow-y-auto p-3">
            {filteredReviews.length === 0 ? (
              <div className="flex h-56 flex-col items-center justify-center gap-3 text-center text-sm text-text-muted">
                <ShieldCheck className="h-8 w-8 text-brand-emerald-bright" />
                <div>{text(source === "loading" ? "正在加载治理队列" : "暂无治理队列项")}</div>
              </div>
            ) : (
              <div className="space-y-2">
                {filteredReviews.map((review) => (
                  <ReviewListItem
                    key={review.id}
                    review={review}
                    selected={selected?.id === review.id}
                    onClick={() => setSelectedId(review.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card variant="data" className="min-h-[560px]">
          {selected ? (
            <ReviewDetail
              review={selected}
              busyDecision={decisionPending}
              onDecision={handleDecision}
            />
          ) : (
            <div className="flex min-h-[480px] flex-col items-center justify-center gap-3 text-center text-sm text-text-muted">
              <ShieldQuestion className="h-10 w-10 text-brand-cyan" />
              <div>{text("请选择一个治理队列项")}</div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function GovernanceStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "orange" | "red" | "blue" | "cyan" | "neutral";
}) {
  const { text } = useI18n();
  const toneClass = {
    emerald: "border-brand-emerald/30 text-brand-emerald-bright",
    orange: "border-brand-orange/30 text-brand-orange",
    red: "border-data-down/30 text-data-down",
    blue: "border-brand-blue/30 text-brand-blue",
    cyan: "border-brand-cyan/30 text-brand-cyan",
    neutral: "border-border-default text-text-secondary",
  }[tone];
  return (
    <div className={cn("rounded-sm border bg-black/38 p-3 shadow-inner-panel", toneClass)}>
      <div className="text-xs text-text-muted">{text(label)}</div>
      <div className="mt-2 font-mono text-2xl text-text-primary">{value}</div>
    </div>
  );
}

function ReviewListItem({
  review,
  selected,
  onClick,
}: {
  review: GovernanceReview;
  selected: boolean;
  onClick: () => void;
}) {
  const { text } = useI18n();
  const meta = statusMeta(review.status);
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-sm border p-3 text-left transition-all",
        selected
          ? "border-brand-cyan/55 bg-brand-cyan/12 shadow-glow-cyan"
          : "border-border-subtle bg-black/34 hover:border-border-strong hover:bg-white/[0.04]"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-text-primary">{reviewTitle(review)}</div>
        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs text-text-muted">
            <span>{text(sourceLabel(review.source))}</span>
            <span className="text-border-strong">/</span>
            <span className="truncate">{text(targetLabel(review.targetTable))}</span>
          </div>
        </div>
        <Badge variant={meta.variant}>{text(meta.label)}</Badge>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 text-caption text-text-muted">
        <span className="truncate">{review.targetKey}</span>
        <span className="shrink-0">{timeAgo(review.createdAt)}</span>
      </div>
    </button>
  );
}

function ReviewDetail({
  review,
  busyDecision,
  onDecision,
}: {
  review: GovernanceReview;
  busyDecision: GovernanceReviewDecision | null;
  onDecision: (decision: GovernanceReviewDecision) => void;
}) {
  const { text } = useI18n();
  const meta = statusMeta(review.status);
  const topLinks = topImpactLinks(review.proposedChange);
  const reviewReasons = stringList(review.proposedChange.review_reasons);
  const eventId = stringValue(review.proposedChange.event_item_id);
  const productionEffect = stringValue(review.proposedChange.production_effect) ?? "none";
  const canDecide = review.status === "pending" && !busyDecision;

  return (
    <div className="space-y-5">
      <CardHeader className="mb-0">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={meta.variant}>{text(meta.label)}</Badge>
            <Badge variant="cyan">{text(sourceLabel(review.source))}</Badge>
            <Badge variant={productionEffect === "none" ? "emerald" : "orange"}>
              {productionEffect === "none" ? text("无生产影响") : productionEffect}
            </Badge>
          </div>
          <CardTitle className="truncate">{reviewTitle(review)}</CardTitle>
          <CardSubtitle>{text("审核结论只进入治理记录；生产写入由目标模块专用流程执行。")}</CardSubtitle>
        </div>
        <DatabaseZap className="h-5 w-5 shrink-0 text-brand-emerald-bright" />
      </CardHeader>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <InfoBlock label="来源" value={text(sourceLabel(review.source))} />
        <InfoBlock label="目标" value={text(targetLabel(review.targetTable))} />
        <InfoBlock label="创建时间" value={new Date(review.createdAt).toLocaleString()} />
      </div>

      {review.reason && (
        <div className="rounded-sm border border-border-subtle bg-black/32 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-text-primary">
            <AlertTriangle className="h-4 w-4 text-brand-orange" />
            {text("入队原因")}
          </div>
          <p className="text-sm leading-6 text-text-secondary">{review.reason}</p>
        </div>
      )}

      {reviewReasons.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            {text("复核原因")}
          </div>
          <div className="flex flex-wrap gap-2">
            {reviewReasons.map((reason) => (
              <Badge key={reason} variant="orange">
                {reviewReasonLabel(reason)}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-sm border border-border-subtle bg-black/32 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
            <Layers3 className="h-4 w-4 text-brand-cyan" />
            {text("变更摘要")}
          </div>
          <ProposalSummary review={review} />
        </div>

        <div className="rounded-sm border border-border-subtle bg-black/32 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
            <ShieldCheck className="h-4 w-4 text-brand-emerald-bright" />
            {text("治理动作")}
          </div>
          {review.status === "pending" ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {ACTIONS.map((action) => {
                const Icon = action.icon;
                return (
                  <Button
                    key={action.decision}
                    variant={action.variant}
                    size="sm"
                    disabled={!canDecide}
                    onClick={() => onDecision(action.decision)}
                    className="justify-start"
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {busyDecision === action.decision ? text("处理中") : text(action.label)}
                  </Button>
                );
              })}
            </div>
          ) : (
            <div className="space-y-3 text-sm text-text-secondary">
              <div className="flex items-center justify-between gap-3 rounded-sm border border-border-subtle bg-black/35 px-3 py-2">
                <span>{text("复核人")}</span>
                <span className="font-mono text-text-primary">{review.reviewedBy ?? "--"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-sm border border-border-subtle bg-black/35 px-3 py-2">
                <span>{text("复核时间")}</span>
                <span className="text-text-primary">
                  {review.reviewedAt ? new Date(review.reviewedAt).toLocaleString() : "--"}
                </span>
              </div>
            </div>
          )}
          {eventId && (
            <Link
              href={`/event-intelligence?event=${encodeURIComponent(eventId)}`}
              className="mt-3 inline-flex h-8 items-center gap-2 rounded-sm border border-brand-cyan/30 bg-brand-cyan/10 px-3 text-xs font-medium text-brand-cyan transition-colors hover:bg-brand-cyan/16"
            >
              {text("打开事件智能")}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
      </div>

      {topLinks.length > 0 && (
        <div className="rounded-sm border border-border-subtle bg-black/32 p-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">{text("候选影响链")}</div>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {topLinks.map((link, index) => (
              <div
                key={`${link.symbol}-${link.mechanism}-${index}`}
                className="rounded-sm border border-border-subtle bg-black/35 p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-mono text-sm text-text-primary">{link.symbol}</div>
                  <Badge variant={link.direction === "bearish" ? "down" : "up"}>
                    {impactDirectionLabel(link.direction)}
                  </Badge>
                </div>
                <div className="mt-2 text-xs text-text-secondary">{mechanismLabel(link.mechanism)}</div>
                <div className="mt-2 flex items-center justify-between text-caption text-text-muted">
                  <span>{link.status ?? "--"}</span>
                  <span className="font-mono text-brand-orange">
                    {link.impactScore === null ? "--" : link.impactScore.toFixed(0)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-sm border border-border-subtle bg-black/42 p-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
          {text("原始治理载荷")}
        </div>
        <pre className="max-h-72 overflow-auto rounded-sm bg-black/45 p-3 text-xs leading-5 text-text-secondary">
          {JSON.stringify(review.proposedChange, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return (
    <div className="rounded-sm border border-border-subtle bg-black/32 p-3">
      <div className="text-xs text-text-muted">{text(label)}</div>
      <div className="mt-2 truncate text-sm font-medium text-text-primary">{value}</div>
    </div>
  );
}

function ProposalSummary({ review }: { review: GovernanceReview }) {
  const { text } = useI18n();
  const payload = review.proposedChange;
  const title = stringValue(payload.title) ?? stringValue(payload.event_title);
  const symbols = stringList(payload.symbols);
  const mechanisms = stringList(payload.mechanisms);
  const changedFields = stringList(payload.changed_fields);
  const eventStatus = stringValue(payload.status) ?? stringValue(payload.after_status);
  const confidence = numberValue(payload.confidence);
  const impactScore = numberValue(payload.impact_score);

  return (
    <div className="space-y-3">
      {title && <p className="text-sm font-medium leading-6 text-text-primary">{title}</p>}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <SummaryRow label="目标键" value={review.targetKey} />
        <SummaryRow label="状态" value={eventStatus ?? review.status} />
        <SummaryRow label="置信度" value={confidence === null ? "--" : `${Math.round(confidence * 100)}%`} />
        <SummaryRow label="影响分" value={impactScore === null ? "--" : impactScore.toFixed(0)} />
      </div>
      <PillGroup label="品种" values={symbols} />
      <PillGroup label="机制" values={mechanisms.map(mechanismLabel)} />
      <PillGroup label="变更字段" values={changedFields} />
      {!title && symbols.length === 0 && mechanisms.length === 0 && changedFields.length === 0 && (
        <div className="text-sm text-text-muted">{text("该队列项没有结构化摘要，请查看原始治理载荷。")}</div>
      )}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return (
    <div className="flex items-center justify-between gap-3 rounded-sm border border-border-subtle bg-black/28 px-3 py-2 text-xs">
      <span className="text-text-muted">{text(label)}</span>
      <span className="truncate font-mono text-text-primary">{value}</span>
    </div>
  );
}

function PillGroup({ label, values }: { label: string; values: string[] }) {
  const { text } = useI18n();
  if (values.length === 0) return null;
  return (
    <div>
      <div className="mb-2 text-xs text-text-muted">{text(label)}</div>
      <div className="flex flex-wrap gap-2">
        {values.slice(0, 12).map((value) => (
          <Badge key={value} variant="neutral">
            {value}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function reviewTitle(review: GovernanceReview): string {
  const payload = review.proposedChange;
  return (
    stringValue(payload.title) ??
    stringValue(payload.event_title) ??
    stringValue(payload.hypothesis_name) ??
    `${targetLabel(review.targetTable)} · ${review.targetKey}`
  );
}

function statusMeta(status: string): {
  label: string;
  variant: "neutral" | "emerald" | "orange" | "cyan" | "critical";
} {
  if (status === "pending") return { label: "待复核", variant: "orange" };
  if (status === "approved") return { label: "已批准", variant: "emerald" };
  if (status === "rejected") return { label: "已驳回", variant: "critical" };
  if (status === "shadow_review") return { label: "影子复核", variant: "cyan" };
  if (status === "reviewed") return { label: "已审查", variant: "emerald" };
  return { label: status, variant: "neutral" };
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    calibration: "校准",
    feedback: "反馈学习",
    event_intelligence: "事件智能",
    llm_agent: "LLM 反思",
    live_divergence: "实盘背离",
  };
  return labels[source] ?? source;
}

function targetLabel(targetTable: string): string {
  const labels: Record<string, string> = {
    signal_calibration: "信号校准",
    event_intelligence_items: "事件智能对象",
    event_impact_links: "事件影响链",
    learning_hypotheses: "学习假设",
    live_divergence_metrics: "实盘背离",
  };
  return labels[targetTable] ?? targetTable;
}

function reviewReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    manual_confirmation_required: "需要人工确认",
    single_source: "单一来源",
    low_confidence: "低置信",
    low_source_reliability: "低来源可信度",
    high_impact_uncertain_event: "高影响不确定事件",
    impact_link_requires_review: "影响链需要复核",
  };
  return labels[reason] ?? reason;
}

function mechanismLabel(mechanism: string): string {
  const labels: Record<string, string> = {
    supply: "供给",
    demand: "需求",
    logistics: "物流",
    policy: "政策",
    inventory: "库存",
    cost: "成本",
    risk_sentiment: "风险情绪",
    geopolitical: "地缘",
    weather: "天气",
    macro: "宏观",
  };
  return labels[mechanism] ?? mechanism;
}

function impactDirectionLabel(direction: string): string {
  const labels: Record<string, string> = {
    bullish: "利多",
    bearish: "利空",
    mixed: "混合",
    watch: "观察",
  };
  return labels[direction] ?? direction;
}

function topImpactLinks(payload: Record<string, unknown>): ImpactLinkSummary[] {
  const rawLinks = Array.isArray(payload.top_links) ? payload.top_links : [];
  return rawLinks.slice(0, 6).flatMap((item) => {
    if (!isObjectRecord(item)) return [];
    const symbol = stringValue(item.symbol);
    const mechanism = stringValue(item.mechanism);
    const direction = stringValue(item.direction);
    if (!symbol || !mechanism || !direction) return [];
    return [
      {
        symbol,
        mechanism,
        direction,
        impactScore: numberValue(item.impact_score),
        status: stringValue(item.status),
      },
    ];
  });
}

function defaultDecisionNote(decision: GovernanceReviewDecision): string {
  const notes: Record<GovernanceReviewDecision, string> = {
    approve: "Governance workbench approved the queued change.",
    reject: "Governance workbench rejected the queued change.",
    mark_reviewed: "Governance workbench marked the queued change as reviewed.",
    shadow_review: "Governance workbench returned the change to shadow review.",
  };
  return notes[decision];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
