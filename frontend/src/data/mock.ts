// Mock data for Zeus prototype demo
// All data is fictional and for visual demonstration only.

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
  freshness: number; // 0-1
  influence: 1 | 2 | 3 | 4;
  active: boolean;
  x?: number;
  y?: number;
  stage?: "source" | "thesis" | "validation" | "impact";
  sector?: "geo" | "energy" | "rubber" | "ferrous" | "positioning";
  tags?: string[];
  tagsZh?: string[];
  tagsEn?: string[];
  narrative?: string;
  narrativeZh?: string | null;
  narrativeEn?: string | null;
  portfolioLinked?: boolean;
  alertLinked?: boolean;
  aggregateCount?: number;
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

export const SECTORS: SectorData[] = [
  {
    id: "ferrous",
    name: "黑色",
    conviction: 0.42,
    symbols: [
      { code: "RB", name: "螺纹钢", change: 1.24, signalActive: true },
      { code: "HC", name: "热卷", change: 0.86, signalActive: false },
      { code: "I", name: "铁矿石", change: -0.32, signalActive: true },
      { code: "J", name: "焦炭", change: 0.51, signalActive: false },
      { code: "JM", name: "焦煤", change: -0.18, signalActive: false },
    ],
  },
  {
    id: "rubber",
    name: "橡胶",
    conviction: -0.31,
    symbols: [
      { code: "RU", name: "天然橡胶", change: -0.92, signalActive: true },
      { code: "NR", name: "20号胶", change: -1.15, signalActive: true },
      { code: "BR", name: "顺丁橡胶", change: 0.21, signalActive: false },
    ],
  },
  {
    id: "energy",
    name: "能化",
    conviction: 0.18,
    symbols: [
      { code: "SC", name: "原油", change: 0.74, signalActive: true },
      { code: "TA", name: "PTA", change: -0.12, signalActive: false },
      { code: "MA", name: "甲醇", change: -0.45, signalActive: false },
      { code: "PP", name: "聚丙烯", change: 0.33, signalActive: false },
    ],
  },
  {
    id: "metals",
    name: "有色",
    conviction: 0.65,
    symbols: [
      { code: "CU", name: "铜", change: 1.42, signalActive: true },
      { code: "AL", name: "铝", change: 0.81, signalActive: false },
      { code: "ZN", name: "锌", change: -0.24, signalActive: false },
      { code: "NI", name: "镍", change: 2.15, signalActive: true },
    ],
  },
  {
    id: "agri",
    name: "农产",
    conviction: -0.12,
    symbols: [
      { code: "M", name: "豆粕", change: -0.41, signalActive: false },
      { code: "Y", name: "豆油", change: 0.18, signalActive: false },
      { code: "P", name: "棕榈油", change: -0.62, signalActive: true },
    ],
  },
  {
    id: "precious",
    name: "贵金属",
    conviction: 0.21,
    symbols: [
      { code: "AU", name: "黄金", change: 0.42, signalActive: false },
      { code: "AG", name: "白银", change: 0.78, signalActive: false },
    ],
  },
];

export const ALERTS: Alert[] = [
  {
    id: "alt-001",
    symbol: "RB2510",
    symbolName: "螺纹钢主力",
    evaluator: "cost_support_pressure",
    severity: "critical",
    confidence: 0.84,
    sampleSize: 47,
    triggeredAt: new Date(Date.now() - 23 * 60_000).toISOString(),
    title: "螺纹跌破 P75 边际成本支撑",
    narrative: "螺纹现货价 4280 已触及高炉成本曲线 P75 分位（4310），连续 2 周持续。结合焦炭弱势 + 钢厂利润率转负 → 触发产能收缩预期。",
    signalChain: [
      "焦煤现货价跌至 P50 分位",
      "焦炭利润率连续 5 日 < -3%",
      "钢厂高炉利润降至 -2.4%",
      "螺纹现货跌破 4310 (P75)",
    ],
    counterEvidence: [
      "螺纹库存仍处年内低位",
      "终端建材采购未出现明显回落",
    ],
    sector: "ferrous",
    regime: "range_high_vol",
    adversarialPassed: true,
  },
  {
    id: "alt-002",
    symbol: "NR2509",
    symbolName: "20号胶主力",
    evaluator: "news_event",
    severity: "high",
    confidence: 0.71,
    sampleSize: 18,
    triggeredAt: new Date(Date.now() - 47 * 60_000).toISOString(),
    title: "泰国天胶产区遭遇暴雨",
    narrative: "泰国南部主产区（合艾、宋卡）出现持续强降雨，未来 7 天预报维持。历史 5 次类似事件 4 次推升 NR 短期上涨 3-7%。",
    signalChain: [
      "气象数据：合艾 24h 降水量 87mm",
      "GORCA 协会发布产区预警",
      "上海保税区报价上调 120 元/吨",
    ],
    counterEvidence: [
      "全球库存仍处历史高位",
      "下游轮胎厂开工率连续 3 周回落",
    ],
    sector: "rubber",
    regime: "trend_up_low_vol",
    adversarialPassed: true,
  },
  {
    id: "alt-003",
    symbol: "CU2502",
    symbolName: "沪铜主力",
    evaluator: "spread_anomaly",
    severity: "high",
    confidence: 0.69,
    sampleSize: 91,
    triggeredAt: new Date(Date.now() - 2 * 3600_000).toISOString(),
    title: "沪伦比价 Z-score 突破 +2.1",
    narrative: "近月沪伦比价偏离 90 日均值 2.1 个标准差，历史回归概率 0.78。结合人民币汇率边际转强 → 套利窗口出现。",
    signalChain: [
      "LME 铜库存连续 5 日下降",
      "国内现货升水扩大至 +180",
      "美元兑人民币汇率走低 0.3%",
    ],
    counterEvidence: [
      "美联储议息会议在即，比价不稳定性升高",
    ],
    sector: "metals",
    regime: "trend_up_low_vol",
    adversarialPassed: true,
  },
  {
    id: "alt-004",
    symbol: "I2509",
    symbolName: "铁矿主力",
    evaluator: "regime_shift",
    severity: "medium",
    confidence: 0.58,
    sampleSize: 32,
    triggeredAt: new Date(Date.now() - 5 * 3600_000).toISOString(),
    title: "铁矿 ATR 放大，趋势进入震荡",
    narrative: "铁矿过去 10 日 ATR 百分位升至 78，ADX 跌至 18，从 trend_down 切换至 range_high_vol。",
    signalChain: [
      "ADX 指标 25 → 18",
      "ATR 百分位 45 → 78",
      "成交量异常放大",
    ],
    counterEvidence: [],
    sector: "ferrous",
    regime: "range_high_vol",
    adversarialPassed: true,
  },
  {
    id: "alt-005",
    symbol: "P2505",
    symbolName: "棕榈油主力",
    evaluator: "inventory_shock",
    severity: "medium",
    confidence: 0.52,
    sampleSize: 24,
    triggeredAt: new Date(Date.now() - 8 * 3600_000).toISOString(),
    title: "马来棕榈油库存意外增加",
    narrative: "MPOB 月报显示库存环比 +5.8%，超预期 +2.1%。供给压力释放，价格短期承压。",
    signalChain: [
      "马来 MPOB 月报库存 +5.8%",
      "印尼出口数据连续放缓",
    ],
    counterEvidence: [
      "原油走强可能拉动生柴需求",
      "国内库存仍处低位",
    ],
    sector: "agri",
    regime: "trend_down_low_vol",
    adversarialPassed: true,
  },
  {
    id: "alt-006",
    symbol: "SC2503",
    symbolName: "原油主力",
    evaluator: "momentum",
    severity: "low",
    confidence: 0.48,
    sampleSize: 56,
    triggeredAt: new Date(Date.now() - 14 * 3600_000).toISOString(),
    title: "原油动量信号触发但置信度偏低",
    narrative: "5 日动量突破 +2.3%，但波动率扩大 + 历史命中率仅 0.52。建议观察 1-2 个交易日确认。",
    signalChain: [
      "5d momentum +2.3%",
      "成交量较 20d 均值 +35%",
    ],
    counterEvidence: [
      "OPEC+ 决议在即，方向不确定",
    ],
    sector: "energy",
    regime: "range_high_vol",
    adversarialPassed: true,
  },
];

export const TRADE_PLANS: TradePlan[] = [
  {
    id: "tp-001",
    alertId: "alt-001",
    symbol: "RB2510",
    symbolName: "螺纹钢主力",
    direction: "long",
    size: 3,
    entryPrice: 4280,
    stopLoss: 4150,
    takeProfit: 4520,
    currentPrice: 4310,
    riskPercent: -3.04,
    rewardPercent: 5.61,
    riskReward: 1.85,
    marginUsage: 18,
    portfolioRisk: 6,
    signalSummary: "成本支撑 + 库存低位 + 历史类比命中率 0.72",
    confidence: 0.84,
    createdAt: new Date(Date.now() - 20 * 60_000).toISOString(),
  },
  {
    id: "tp-002",
    alertId: "alt-002",
    symbol: "NR2509",
    symbolName: "20号胶主力",
    direction: "long",
    size: 2,
    entryPrice: 14250,
    stopLoss: 13800,
    takeProfit: 15100,
    currentPrice: 14180,
    riskPercent: -3.16,
    rewardPercent: 5.96,
    riskReward: 1.89,
    marginUsage: 12,
    portfolioRisk: 4,
    signalSummary: "产区暴雨 + 历史 4/5 命中 + 保税区报价跟涨",
    confidence: 0.71,
    createdAt: new Date(Date.now() - 45 * 60_000).toISOString(),
  },
  {
    id: "tp-003",
    alertId: "alt-003",
    symbol: "CU2502",
    symbolName: "沪铜主力",
    direction: "short",
    size: 1,
    entryPrice: 78950,
    stopLoss: 80200,
    takeProfit: 76500,
    currentPrice: 78420,
    riskPercent: -1.58,
    rewardPercent: 3.10,
    riskReward: 1.96,
    marginUsage: 9,
    portfolioRisk: 3,
    signalSummary: "沪伦比 Z=+2.1 + 历史回归概率 0.78",
    confidence: 0.69,
    createdAt: new Date(Date.now() - 110 * 60_000).toISOString(),
  },
];

export const POSITIONS: Position[] = [
  {
    id: "pos-001",
    symbol: "RB2510",
    symbolName: "螺纹钢主力",
    direction: "long",
    lots: 3,
    avgEntry: 4280,
    currentPrice: 4310,
    pnl: 9000,
    pnlPercent: 0.70,
    openDate: "2026-04-26",
    sector: "ferrous",
  },
  {
    id: "pos-002",
    symbol: "NR2509",
    symbolName: "20号胶主力",
    direction: "long",
    lots: 2,
    avgEntry: 14250,
    currentPrice: 14180,
    pnl: -700,
    pnlPercent: -0.49,
    openDate: "2026-04-28",
    sector: "rubber",
  },
];

export const CAUSAL_NODES: CausalNode[] = [
  { id: "n1", type: "event", label: "美国航母移动", freshness: 0.9, influence: 3, active: true },
  { id: "n2", type: "event", label: "中东局势升级", freshness: 0.85, influence: 4, active: true },
  { id: "n3", type: "alert", label: "原油 SC 上涨预期", freshness: 1.0, influence: 4, active: true },
  { id: "n4", type: "signal", label: "化工链上行", freshness: 0.7, influence: 3, active: false },
  { id: "n5", type: "metric", label: "PTA 现货上涨", freshness: 0.6, influence: 2, active: false },
  { id: "n6", type: "metric", label: "PP 走强", freshness: 0.5, influence: 2, active: false },
  { id: "n7", type: "counter", label: "CFTC 持仓未增", freshness: 0.4, influence: 1, active: false },
  { id: "n8", type: "event", label: "产区暴雨", freshness: 1.0, influence: 3, active: true },
  { id: "n9", type: "signal", label: "NR/RU 短期看涨", freshness: 0.95, influence: 3, active: true },
  { id: "n10", type: "metric", label: "焦煤价格回落", freshness: 0.55, influence: 2, active: false },
  { id: "n11", type: "metric", label: "高炉利润转负", freshness: 0.7, influence: 3, active: true },
  { id: "n12", type: "alert", label: "螺纹成本支撑", freshness: 0.95, influence: 4, active: true },
];

export const CAUSAL_EDGES: CausalEdge[] = [
  { id: "e1", source: "n1", target: "n2", confidence: 0.82, lag: "1d", hitRate: 0.78, direction: "neutral", verified: true },
  { id: "e2", source: "n2", target: "n3", confidence: 0.71, lag: "3-7d", hitRate: 0.69, direction: "bullish", verified: true },
  { id: "e3", source: "n7", target: "n3", confidence: 0.45, lag: "0d", hitRate: 0.30, direction: "bearish", verified: false },
  { id: "e4", source: "n3", target: "n4", confidence: 0.65, lag: "5-10d", hitRate: 0.61, direction: "bullish", verified: true },
  { id: "e5", source: "n4", target: "n5", confidence: 0.78, lag: "1-3d", hitRate: 0.72, direction: "bullish", verified: true },
  { id: "e6", source: "n4", target: "n6", confidence: 0.74, lag: "1-3d", hitRate: 0.68, direction: "bullish", verified: true },
  { id: "e7", source: "n8", target: "n9", confidence: 0.85, lag: "1-2d", hitRate: 0.80, direction: "bullish", verified: true },
  { id: "e8", source: "n10", target: "n11", confidence: 0.72, lag: "5d", hitRate: 0.66, direction: "bearish", verified: true },
  { id: "e9", source: "n11", target: "n12", confidence: 0.84, lag: "10d", hitRate: 0.74, direction: "bearish", verified: true },
];

export const HEARTBEAT_STATE = {
  dataAge: "14s",
  activeSignals: 17,
  drift: "正常",
  driftStatus: "healthy" as "healthy" | "warning" | "alert",
  calibrationProgress: 73,
  calibrationTarget: 100,
  regime: "range_high_vol",
};

export const PERSONAL_GREETING = {
  greeting: "晚上好",
  username: "Nikoo",
  hoursSinceLastVisit: 14,
  alertsSinceLastVisit: 12,
  alertsRelevantToPosition: 3,
  highlight: "RB 触发了 cost_support_pressure",
};

// Sector heatmap conviction colors
export const SECTOR_COLORS: Record<Sector, string> = {
  ferrous: "#475569",
  energy: "#7c2d12",
  agri: "#166534",
  metals: "#92400e",
  precious: "#854d0e",
  rubber: "#365314",
};

export const REGIME_LABEL: Record<string, string> = {
  trend_up_low_vol: "趋势上行 · 低波动",
  trend_down_low_vol: "趋势下行 · 低波动",
  range_high_vol: "震荡 · 高波动",
  range_low_vol: "震荡 · 低波动",
};
