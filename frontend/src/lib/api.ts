import type { Alert, Position, Sector, Severity } from "@/data/mock";

const SEVERITIES = new Set<Severity>(["critical", "high", "medium", "low"]);

export interface PortfolioPosition extends Position {
  marginUsed: number;
  status: string;
  dataTimestamp?: string;
  vintageAt?: string;
}

export interface RiskVarResult {
  var95: number;
  var99: number;
  cvar95: number;
  cvar99: number;
  horizon: number;
  method: string;
  calculated_at: string;
}

export interface StressTestResult {
  scenario: string;
  description: string;
  portfolio_pnl: number;
  position_impacts: { position_id: string; strategy_name: string; pnl: number }[];
}

export interface CorrelationMatrix {
  symbols: string[];
  matrix: number[][];
  window: number;
  calculated_at: string;
}

export interface PortfolioSnapshot {
  positions: PortfolioPosition[];
  varResult: RiskVarResult | null;
  stressResults: StressTestResult[];
  correlation: CorrelationMatrix | null;
}

export interface AttributionSlice {
  label: string;
  samples: number;
  wins: number;
  win_rate: number;
  expected_pnl: number;
  avg_mae: number;
  avg_mfe: number;
}

export interface AttributionReport {
  period_start: string;
  period_end: string;
  total_recommendations: number;
  closed_recommendations: number;
  win_rate: number;
  expected_pnl: number;
  slices: Record<string, AttributionSlice[]>;
  risk_assessment: {
    stop_loss?: { p50_mae: number; p80_mae: number; note: string };
    take_profit?: { p50_mfe: number; p80_mfe: number; note: string };
  };
}

export interface NewsEvent {
  id: string;
  source: string;
  rawUrl?: string | null;
  title: string;
  summary: string;
  publishedAt: string;
  eventType: string;
  affectedSymbols: string[];
  direction: "bullish" | "bearish" | "mixed" | "unclear";
  severity: number;
  timeHorizon: string;
  confidence: number;
  sourceCount: number;
  verificationStatus: string;
  requiresManualConfirmation: boolean;
}

interface BackendAlert {
  id: string;
  title: string;
  summary: string;
  severity: string;
  category: string;
  type: string;
  triggered_at: string;
  confidence: number;
  adversarial_passed?: boolean;
  llm_involved?: boolean;
  confidence_tier?: string;
  human_action_required?: boolean;
  human_action_deadline?: string | null;
  dedup_suppressed?: boolean;
  related_assets: string[];
  trigger_chain: { label?: string; description?: string }[];
  risk_items: string[];
  manual_check_items: string[];
}

interface BackendNewsEvent {
  id: string;
  source: string;
  raw_url?: string | null;
  title: string;
  summary: string;
  published_at: string;
  event_type: string;
  affected_symbols: string[];
  direction: string;
  severity: number;
  time_horizon: string;
  llm_confidence: number;
  source_count: number;
  verification_status: string;
  requires_manual_confirmation: boolean;
}

interface BackendPosition {
  id: string;
  strategy_name?: string | null;
  legs: BackendLeg[];
  opened_at: string;
  unrealized_pnl: number;
  total_margin_used: number;
  status: string;
  manual_entry?: boolean;
  monitoring_priority?: number;
  propagation_nodes?: { symbol: string; category: string; relationship: string }[];
  data_mode?: string;
}

interface BackendLeg {
  asset?: string;
  symbol?: string;
  direction?: string;
  size?: number;
  quantity?: number;
  lots?: number;
  unit?: string;
  entryPrice?: number;
  entry_price?: number;
  avgEntry?: number;
  currentPrice?: number;
  current_price?: number;
  price?: number;
}

interface BackendMarketData {
  symbol: string;
  timestamp: string;
  close: number;
  vintage_at?: string;
  ingested_at?: string;
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T;
}

export async function fetchAlertsFromApi(): Promise<Alert[]> {
  const alerts = await fetchJson<BackendAlert[]>("/api/alerts?limit=100");
  return alerts.map(mapAlert);
}

export async function fetchPortfolioSnapshot(): Promise<PortfolioSnapshot> {
  const [positions, varEnvelope, stressEnvelope] = await Promise.all([
    fetchJson<BackendPosition[]>("/api/positions?status_filter=open&limit=500"),
    fetchJson<ApiEnvelope<RiskVarResult>>("/api/risk/var"),
    fetchJson<ApiEnvelope<StressTestResult[]>>("/api/risk/stress"),
  ]);

  const symbols = uniqueSymbols(positions);
  const latestRows = await fetchLatestMarketRows(symbols);
  const mappedPositions = positions.map((position) => mapPosition(position, latestRows));

  const correlation =
    symbols.length > 0
      ? await fetchJson<ApiEnvelope<CorrelationMatrix>>(
          `/api/risk/correlation?symbols=${encodeURIComponent(symbols.join(","))}&window=60`
        ).then((response) => response.data)
      : null;

  return {
    positions: mappedPositions,
    varResult: varEnvelope.data,
    stressResults: stressEnvelope.data,
    correlation,
  };
}

export async function fetchNewsEventsFromApi(): Promise<NewsEvent[]> {
  const rows = await fetchJson<BackendNewsEvent[]>("/api/news-events?limit=200");
  return rows.map(mapNewsEvent);
}

export async function fetchAttributionReport(): Promise<AttributionReport> {
  return fetchJson<AttributionReport>("/api/attribution/report");
}

export async function submitAlertFeedback(
  alertId: string,
  agree: "agree" | "disagree" | "uncertain",
  willTrade: "will_trade" | "will_not_trade" | "partial"
): Promise<void> {
  await fetchJson("/api/feedback", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      alert_id: alertId,
      agree,
      will_trade: willTrade,
    }),
  });
}

export async function submitHumanDecision(
  alertId: string,
  decision: "approve" | "reject" | "modify",
  reasoning?: string
): Promise<void> {
  await fetchJson("/api/arbitration/decisions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      alert_id: alertId,
      decision,
      reasoning,
      decided_by: "zeus-ui",
    }),
  });
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function fetchLatestMarketRows(symbols: string[]): Promise<Map<string, BackendMarketData>> {
  const entries = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const row = await fetchJson<BackendMarketData>(
          `/api/market-data/symbols/${encodeURIComponent(symbol)}/latest`
        );
        return [symbol, row] as const;
      } catch {
        return [symbol, null] as const;
      }
    })
  );

  return new Map(entries.filter((entry): entry is readonly [string, BackendMarketData] => entry[1] !== null));
}

function mapNewsEvent(event: BackendNewsEvent): NewsEvent {
  return {
    id: event.id,
    source: event.source,
    rawUrl: event.raw_url,
    title: event.title,
    summary: event.summary,
    publishedAt: event.published_at,
    eventType: event.event_type,
    affectedSymbols: event.affected_symbols,
    direction: toNewsDirection(event.direction),
    severity: event.severity,
    timeHorizon: event.time_horizon,
    confidence: event.llm_confidence,
    sourceCount: event.source_count,
    verificationStatus: event.verification_status,
    requiresManualConfirmation: event.requires_manual_confirmation,
  };
}

function mapAlert(alert: BackendAlert): Alert {
  const symbol = alert.related_assets[0] ?? "N/A";
  return {
    id: alert.id,
    symbol,
    symbolName: symbol,
    evaluator: alert.type,
    severity: toSeverity(alert.severity),
    confidence: alert.confidence,
    sampleSize: alert.trigger_chain.length,
    triggeredAt: alert.triggered_at,
    title: alert.title,
    narrative: alert.summary,
    signalChain: alert.trigger_chain.map((step) => step.description || step.label || "trigger"),
    counterEvidence: alert.risk_items,
    sector: categoryToSector(alert.category),
    regime: alert.category,
    adversarialPassed: Boolean(alert.adversarial_passed),
    confidenceTier: alert.confidence_tier,
    humanActionRequired: Boolean(alert.human_action_required),
    humanActionDeadline: alert.human_action_deadline,
    llmInvolved: Boolean(alert.llm_involved),
    dedupSuppressed: Boolean(alert.dedup_suppressed),
  };
}

function toNewsDirection(value: string): NewsEvent["direction"] {
  if (value === "bullish" || value === "bearish" || value === "mixed") return value;
  return "unclear";
}

function mapPosition(
  position: BackendPosition,
  latestRows: Map<string, BackendMarketData>
): PortfolioPosition {
  const firstLeg = position.legs[0] ?? {};
  const symbol = String(firstLeg.asset || firstLeg.symbol || position.strategy_name || position.id);
  const latest = latestRows.get(symbol);
  const lots = sum(position.legs.map((leg) => numeric(leg.size, leg.quantity, leg.lots)));
  const avgEntry = weightedAverage(position.legs, "entry");
  const currentPrice = latest?.close ?? weightedAverage(position.legs, "current");
  const notional = Math.abs(avgEntry * Math.max(lots, 1));
  const pnlPercent = notional > 0 ? (position.unrealized_pnl / notional) * 100 : 0;

  return {
    id: position.id,
    symbol,
    symbolName: position.strategy_name || symbol,
    direction: firstLeg.direction === "short" ? "short" : "long",
    lots,
    avgEntry,
    currentPrice,
    pnl: position.unrealized_pnl,
    pnlPercent,
    openDate: position.opened_at.slice(0, 10),
    sector: guessSector(symbol),
    manualEntry: Boolean(position.manual_entry),
    monitoringPriority: position.monitoring_priority,
    propagationNodes: position.propagation_nodes,
    dataMode: position.data_mode,
    marginUsed: position.total_margin_used,
    status: position.status,
    dataTimestamp: latest?.timestamp,
    vintageAt: latest?.vintage_at || latest?.ingested_at,
  };
}

function uniqueSymbols(positions: BackendPosition[]): string[] {
  return Array.from(
    new Set(
      positions.flatMap((position) =>
        position.legs
          .map((leg) => String(leg.asset || leg.symbol || "").trim())
          .filter((symbol) => symbol.length > 0)
      )
    )
  ).sort();
}

function weightedAverage(legs: BackendLeg[], mode: "entry" | "current"): number {
  let numerator = 0;
  let denominator = 0;
  for (const leg of legs) {
    const size = numeric(leg.size, leg.quantity, leg.lots);
    const price =
      mode === "entry"
        ? numeric(leg.entryPrice, leg.entry_price, leg.avgEntry)
        : numeric(leg.currentPrice, leg.current_price, leg.price);
    if (size > 0 && price > 0) {
      numerator += price * size;
      denominator += size;
    }
  }
  return denominator > 0 ? numerator / denominator : 0;
}

function toSeverity(value: string): Severity {
  return SEVERITIES.has(value as Severity) ? (value as Severity) : "low";
}

function categoryToSector(category: string): Sector {
  if (category === "agriculture") return "agri";
  if (category === "nonferrous") return "metals";
  if (category === "energy") return "energy";
  if (category === "ferrous") return "ferrous";
  if (category === "rubber") return "rubber";
  return "precious";
}

function guessSector(symbol: string): Sector {
  const prefix = symbol.replace(/\d+/g, "").toUpperCase();
  if (["RB", "HC", "I", "J", "JM", "SF", "SM"].includes(prefix)) return "ferrous";
  if (["RU", "NR", "BR"].includes(prefix)) return "rubber";
  if (["SC", "FU", "TA", "EG", "MA", "PP"].includes(prefix)) return "energy";
  if (["CU", "AL", "ZN", "NI", "SN", "PB"].includes(prefix)) return "metals";
  if (["M", "Y", "P", "C", "A"].includes(prefix)) return "agri";
  return "precious";
}

function numeric(...values: unknown[]): number {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return 0;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
