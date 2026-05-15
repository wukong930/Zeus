export type Severity = "critical" | "high" | "medium" | "low";
export type Direction = "long" | "short";
export type Sector = "ferrous" | "energy" | "agri" | "metals" | "precious" | "rubber";

export interface Alert {
  id: string;
  symbol: string;
  symbolName: string;
  evaluator: string;
  severity: Severity;
  confidence: number;
  sampleSize: number;
  triggeredAt: string;
  title: string;
  narrative: string;
  signalChain: string[];
  counterEvidence: string[];
  sector: Sector;
  regime: string;
  adversarialPassed: boolean;
  confidenceTier?: string;
  humanActionRequired?: boolean;
  humanActionDeadline?: string | null;
  llmInvolved?: boolean;
  dedupSuppressed?: boolean;
}

export interface TradePlan {
  id: string;
  alertId: string;
  status: string;
  reviewRequired: boolean;
  symbol: string;
  symbolName: string;
  direction: Direction;
  size: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  currentPrice: number;
  riskPercent: number;
  rewardPercent: number;
  riskReward: number;
  marginUsage: number;
  portfolioRisk: number;
  signalSummary: string;
  confidence: number;
  sampleSize: number;
  createdAt: string;
}

export interface Position {
  id: string;
  symbol: string;
  symbolName: string;
  direction: Direction;
  lots: number;
  avgEntry: number;
  currentPrice: number;
  pnl: number;
  pnlPercent: number;
  openDate: string;
  sector: Sector;
  manualEntry?: boolean;
  monitoringPriority?: number;
  dataMode?: string;
  propagationNodes?: { symbol: string; category: string; relationship: string }[];
}

export interface SectorData {
  id: Sector;
  name: string;
  conviction: number;
  symbols: { code: string; name: string; change: number; signalActive: boolean }[];
}

export interface CausalNode {
  id: string;
  type: "event" | "signal" | "metric" | "alert" | "counter" | "cluster";
  label: string;
  labelZh?: string | null;
  labelEn?: string | null;
  freshness: number;
  influence: 1 | 2 | 3 | 4;
  active: boolean;
  x?: number;
  y?: number;
  stage?: "source" | "thesis" | "validation" | "impact";
  sector?:
    | "geo"
    | "energy"
    | "rubber"
    | "ferrous"
    | "metals"
    | "agri"
    | "precious"
    | "positioning";
  tags?: string[];
  tagsZh?: string[];
  tagsEn?: string[];
  narrative?: string;
  narrativeZh?: string | null;
  narrativeEn?: string | null;
  portfolioLinked?: boolean;
  alertLinked?: boolean;
  aggregateCount?: number;
  evidence?: CausalEvidenceItem[];
  counterEvidence?: CausalEvidenceItem[];
  qualityStatus?: "blocked" | "review" | "shadow_ready" | "decision_grade" | null;
  qualityScore?: number | null;
  qualityIssues?: string[];
}

export interface CausalEvidenceItem {
  kind: "evidence" | "counterevidence";
  text: string;
  textZh?: string | null;
  textEn?: string | null;
  source?: string | null;
}

export interface CausalEdge {
  id: string;
  source: string;
  target: string;
  confidence: number;
  lag: string;
  hitRate: number;
  direction: "bullish" | "bearish" | "neutral";
  verified: boolean;
}
