import type {
  Alert,
  CausalEdge,
  CausalNode,
  Direction,
  Position,
  Sector,
  SectorData,
  Severity,
  TradePlan,
} from "@/lib/domain";

const SEVERITIES = new Set<Severity>(["critical", "high", "medium", "low"]);
const DEFAULT_API_TIMEOUT_MS = 15_000;

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
  degraded?: boolean;
  unavailableSections?: string[];
}

export interface SectorSnapshot {
  sectors: SectorData[];
  degraded: boolean;
  unavailableSections: string[];
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
    stop_loss?: { p50_mae: number | null; p80_mae: number | null; note: string };
    take_profit?: { p50_mfe: number | null; p80_mfe: number | null; note: string };
  };
}

export interface CostComponent {
  name: string;
  value: number;
  unit: string;
  source: string;
  uncertainty_pct: number;
}

export interface CostInput {
  name: string;
  value: number;
  unit: string;
  source: string;
  updated_at?: string | null;
  uncertainty_pct: number;
}

export interface CostModel {
  symbol: string;
  name: string;
  sector: string;
  current_price: number | null;
  total_unit_cost: number;
  breakevens: {
    p25: number;
    p50: number;
    p75: number;
    p90: number;
  };
  profit_margin: number | null;
  cost_breakdown: CostComponent[];
  inputs: Record<string, CostInput>;
  data_sources: {
    name: string;
    unit?: string;
    updated_at?: string | null;
    uncertainty_pct?: number;
  }[];
  uncertainty_pct: number;
  formula_version: string;
}

export interface CostSnapshot {
  id: string;
  symbol: string;
  name: string;
  sector: string;
  snapshot_date: string;
  current_price: number | null;
  total_unit_cost: number;
  breakeven_p25: number;
  breakeven_p50: number;
  breakeven_p75: number;
  breakeven_p90: number;
  profit_margin: number | null;
  uncertainty_pct: number;
  formula_version: string;
  created_at: string;
}

export interface CostChain {
  sector: string;
  symbols: string[];
  results: Record<string, CostModel>;
}

export interface CostSimulationRequest {
  inputs_by_symbol: Record<string, Record<string, number>>;
  current_prices: Record<string, number | null>;
}

export interface CostBenchmarkComparison {
  symbol: string;
  metric: string;
  model_value: number;
  public_value: number;
  error_pct: number;
  within_tolerance: boolean;
  source: string;
  observed_at: string;
  note: string;
}

export interface CostSignalCase {
  case_id: string;
  title: string;
  expected_signals: string[];
  triggered_signals: string[];
  passed: boolean;
  note: string;
}

export interface CostQualityReport {
  sector: string;
  generated_at: string;
  benchmark_error_avg_pct: number;
  benchmark_error_max_pct: number;
  benchmark_pass_rate: number;
  signal_case_hit_rate: number;
  data_quality_score: number;
  paid_data_recommendation: string;
  preferred_vendor: string | null;
  benchmark_comparisons: CostBenchmarkComparison[];
  signal_cases: CostSignalCase[];
  limitations: string[];
}

export interface CausalWebGraph {
  generated_at: string;
  nodes: CausalNode[];
  edges: CausalEdge[];
  source_counts: Record<string, number>;
}

export type WorldRiskLevel = "low" | "watch" | "elevated" | "high" | "critical";
export type WorldMapDataQuality = "runtime" | "partial" | "baseline";
export type WorldMapLayerStatus = "ready" | "baseline" | "planned";
export type WorldMapRiskMomentumDirection = "rising" | "easing" | "steady";
export type WorldMapStoryStage =
  | "climate"
  | "weather_regime"
  | "production"
  | "logistics"
  | "supply"
  | "demand"
  | "inventory"
  | "policy"
  | "cost"
  | "market";
export type WorldMapEvidenceKind =
  | "weather"
  | "alert"
  | "news"
  | "signal"
  | "position"
  | "event_intelligence"
  | "baseline";
export type WorldMapRiskFactor =
  | "rainfall_surplus"
  | "drought_heat"
  | "el_nino"
  | "supply_disruption"
  | "logistics_disruption"
  | "inventory_pressure"
  | "policy_shift"
  | "demand_shift"
  | "energy_cost";

export interface GeoPoint {
  lat: number;
  lon: number;
}

export interface WorldMapWeather {
  precipitationAnomalyPct: number;
  rainfall7dMm: number;
  temperatureAnomalyC: number;
  floodRisk: number;
  droughtRisk: number;
  precipitationPercentile?: number | null;
  temperaturePercentile?: number | null;
  currentTemperatureC?: number | null;
  precipitation1hMm?: number | null;
  humidityPct?: number | null;
  windKph?: number | null;
  dataSource: string;
  confidence: number;
}

export interface WorldMapRuntime {
  alerts: number;
  highSeverityAlerts: number;
  newsEvents: number;
  signals: number;
  positions: number;
  eventIntelligence: number;
  latestEventAt: string | null;
}

export interface WorldMapEventQuality {
  status: EventIntelligenceQualityStatus | null;
  score: number;
  total: number;
  blocked: number;
  review: number;
  shadowReady: number;
  decisionGrade: number;
  passed: number;
}

export interface WorldMapEvidenceHealth {
  evidenceCount: number;
  counterEvidenceCount: number;
  runtimeSources: number;
  freshRuntimeSources: number;
  sourceReliability: number;
  freshnessScore: number;
  densityScore: number;
}

export interface WorldMapRiskMomentum {
  direction: WorldMapRiskMomentumDirection;
  delta: number;
  intensity: number;
  driverZh: string;
  driverEn: string;
  reasonZh: string;
  reasonEn: string;
  changedAt: string | null;
}

export interface WorldMapDriver {
  labelZh: string;
  labelEn: string;
  weight: number;
}

export interface WorldMapEvidenceItem {
  kind: WorldMapEvidenceKind;
  titleZh: string;
  titleEn: string;
  source: string;
  weight: number;
}

export interface WorldMapStoryStep {
  stage: WorldMapStoryStage;
  labelZh: string;
  labelEn: string;
  confidence: number;
  evidenceKind: WorldMapEvidenceKind;
}

export interface WorldMapRiskStory {
  headlineZh: string;
  headlineEn: string;
  triggerZh: string;
  triggerEn: string;
  chain: WorldMapStoryStep[];
  evidence: WorldMapEvidenceItem[];
  counterEvidence: WorldMapEvidenceItem[];
}

export interface WorldMapAdaptiveAlert {
  id: string;
  titleZh: string;
  titleEn: string;
  severity: WorldRiskLevel;
  triggerZh: string;
  triggerEn: string;
  mechanismZh: string;
  mechanismEn: string;
  confidence: number;
  source: WorldMapEvidenceKind;
}

export interface WorldMapCausalScope {
  regionId: string;
  symbols: string[];
  eventIds: string[];
  causalWebUrl: string;
  hasDirectLinks: boolean;
}

export interface WorldMapFilterOption {
  id: string;
  labelZh: string;
  labelEn: string;
}

export interface WorldMapFilterOptions {
  symbols: string[];
  mechanisms: WorldMapFilterOption[];
  sources: WorldMapFilterOption[];
}

export interface WorldMapRegion {
  id: string;
  nameZh: string;
  nameEn: string;
  commodityZh: string;
  commodityEn: string;
  symbols: string[];
  center: GeoPoint;
  polygon: GeoPoint[];
  riskScore: number;
  riskLevel: WorldRiskLevel;
  riskMomentum?: WorldMapRiskMomentum;
  drivers: WorldMapDriver[];
  weather: WorldMapWeather;
  runtime: WorldMapRuntime;
  story: WorldMapRiskStory;
  adaptiveAlerts: WorldMapAdaptiveAlert[];
  causalScope: WorldMapCausalScope;
  mechanisms: WorldMapRiskFactor[];
  sourceKinds: WorldMapEvidenceKind[];
  eventQuality: WorldMapEventQuality;
  evidenceHealth?: WorldMapEvidenceHealth;
  narrativeZh: string;
  narrativeEn: string;
  dataQuality: WorldMapDataQuality;
}

export interface WorldMapLayer {
  id: string;
  labelZh: string;
  labelEn: string;
  status: WorldMapLayerStatus;
  enabled: boolean;
}

export interface WorldMapSummary {
  regions: number;
  elevatedRegions: number;
  maxRiskScore: number;
  runtimeLinkedRegions: number;
}

export interface WorldMapSnapshot {
  generatedAt: string;
  summary: WorldMapSummary;
  filters: WorldMapFilterOptions;
  layers: WorldMapLayer[];
  regions: WorldMapRegion[];
}

export type WorldMapTileLayer = "weather" | "risk";
export type WorldMapTileLayerFilter = "all" | WorldMapTileLayer;
export type WorldMapTileResolution = "coarse" | "medium";
export type WorldMapTileMetric =
  | "precipitation_anomaly_pct"
  | "flood_risk"
  | "drought_risk"
  | "composite_risk";

export interface WorldMapTileCell {
  id: string;
  layer: WorldMapTileLayer;
  regionId: string;
  center: GeoPoint;
  polygon: GeoPoint[];
  metric: WorldMapTileMetric;
  value: number;
  intensity: number;
  riskLevel: WorldRiskLevel;
  dataQuality: WorldMapDataQuality;
  source: string;
}

export interface WorldMapTileSummary {
  weatherCells: number;
  riskCells: number;
  maxIntensity: number;
  dataSources: string[];
}

export interface WorldMapTileSnapshot {
  generatedAt: string;
  resolution: WorldMapTileResolution;
  layer: WorldMapTileLayerFilter;
  summary: WorldMapTileSummary;
  cells: WorldMapTileCell[];
}

export interface DataSourceStatus {
  id: string;
  name: string;
  category: string;
  enabled: boolean;
  configured: boolean;
  requires_key: boolean;
  free_tier: string;
  status: string;
  note: string;
}

export interface ContractMetadata {
  id: string;
  symbol: string;
  exchange: string | null;
  commodity: string | null;
  contract_month: string;
  expiry_date: string | null;
  is_main: boolean;
  main_from: string | null;
  main_until: string | null;
  volume: number | null;
  open_interest: number | null;
  created_at: string;
  updated_at: string;
}

export interface SchedulerJobStatus {
  id: string;
  name: string;
  cron: string;
  enabled: boolean;
  running: boolean;
  last_run: string | null;
  last_result: string | null;
  last_error: string | null;
  consecutive_failures: number;
  status: string;
}

export interface SchedulerHealth {
  total_jobs: number;
  enabled_jobs: number;
  degraded_jobs: string[];
  warning_jobs: string[];
  unconfigured_jobs: string[];
  last_activity: string | null;
  jobs: Pick<SchedulerJobStatus, "id" | "name" | "status" | "last_run" | "last_error">[];
}

export interface SchedulerSnapshot {
  jobs: SchedulerJobStatus[];
  health: SchedulerHealth;
}

export interface LLMUsageSummary {
  module: string;
  period_start: string;
  period_end: string;
  calls: number;
  cache_hits: number;
  estimated_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface LLMProviderSettings {
  provider: string;
  name: string;
  model: string | null;
  configured: boolean;
  active: boolean;
  source: string;
  status: string;
  reason: string | null;
}

export interface AlertDedupSettings {
  repeat_window_hours: number;
  combination_window_hours: number;
  daily_alert_limit: number;
  allow_severity_upgrade_resend: boolean;
  source: string;
}

export interface NotificationSettings {
  realtime_sse: boolean;
  feishu_webhook: boolean;
  email: boolean;
  custom_webhook: boolean;
  source: string;
}

export interface AdversarialRuntimeSettings {
  warmup_enabled: boolean;
  mode: "warmup" | "enforcing" | string;
  historical_combo_mode: "informational" | "sample_based_enforcing" | string;
  production_effect: "observe_only" | "may_suppress_signals" | string;
  source: string;
}

export type NotificationSettingsUpdate = Partial<
  Pick<
    NotificationSettings,
    "realtime_sse" | "feishu_webhook" | "email" | "custom_webhook"
  >
>;

export type AdversarialRuntimeSettingsUpdate = Pick<
  AdversarialRuntimeSettings,
  "warmup_enabled"
>;

export interface ScenarioSimulationRequest {
  target_symbol: string;
  shocks: Record<string, number>;
  base_price?: number | null;
  days: number;
  simulations: number;
  volatility_pct?: number | null;
  drift_pct?: number;
  seed?: number;
  max_depth?: number;
}

export interface ScenarioPropagationPath {
  root_symbol: string;
  source_symbol: string;
  target_symbol: string;
  relationship: string;
  elasticity: number;
  input_shock: number;
  impact: number;
  depth: number;
  lag_days: number;
}

export interface ScenarioImpact {
  symbol: string;
  direct_shock: number;
  propagated_shock: number;
  total_shock: number;
  dominant_driver: string | null;
  paths: ScenarioPropagationPath[];
}

export interface ScenarioReport {
  scenario_id: string;
  generated_at: string;
  status: string;
  target_symbol: string;
  base_price: number;
  base_price_source: string;
  degraded: boolean;
  unavailable_sections: string[];
  what_if: {
    shocks: Record<string, number>;
    impacts: ScenarioImpact[];
    key_paths: ScenarioPropagationPath[];
    max_depth: number;
  };
  monte_carlo: {
    target_symbol: string;
    base_price: number;
    days: number;
    simulations: number;
    volatility_pct: number;
    drift_pct: number;
    applied_shock: number;
    terminal_distribution: Record<"p5" | "p25" | "p50" | "p75" | "p95", number>;
    expected_terminal_price: number;
    expected_return: number;
    downside_probability: number;
    sample_paths: number[][];
    seed: number;
  };
  narrative: string;
  narrative_source: string;
  risk_points: string[];
  suggested_actions: string[];
}

export interface BacktestRegimeProfile {
  regime: string;
  sample_size: number;
  win_rate: number;
  sharpe: number;
  max_drawdown: number;
  cvar95: number;
}

export interface BacktestPathMetrics {
  total_return: number;
  max_drawdown: number;
  underwater_durations: number[];
  pain_ratio: number;
  recovery_factor: number;
  cvar95: number;
  mae_p50: number | null;
  mae_p80: number | null;
  mfe_p50: number | null;
  mfe_p80: number | null;
}

export interface BacktestQualitySummary {
  as_of: string;
  source: string;
  sample_size: number;
  degraded: boolean;
  unavailable_sections: string[];
  walk_forward: {
    training_years: number;
    test_months: number;
    step_months: number;
    mode: string;
  };
  regime_profile: BacktestRegimeProfile[];
  path_metrics: BacktestPathMetrics;
  universe: {
    as_of: string;
    requested_symbols: string[];
    active_symbols: string[];
    missing_symbols: string[];
    valid: boolean;
  };
  guardrails: {
    calibration_strategy: string;
    multiple_testing: string;
    slippage_model: string;
    decision_grade_required: boolean;
  };
}

export interface ReliabilityBin {
  lower: number;
  upper: number;
  samples: number;
  avg_confidence: number | null;
  hit_rate: number | null;
  calibration_gap: number | null;
}

export interface IsotonicPoint {
  confidence: number;
  calibrated_probability: number;
  samples: number;
}

export interface ThresholdCalibrationReport {
  signal_type: string | null;
  category: string | null;
  samples: number;
  hits: number;
  misses: number;
  brier_score: number | null;
  expected_calibration_error: number | null;
  projected_calibration_error: number | null;
  calibration_error_improvement: number | null;
  bins: ReliabilityBin[];
  isotonic_curve: IsotonicPoint[];
  current_thresholds: Record<"auto" | "notify", number>;
  suggested_thresholds: Record<"auto" | "notify", number>;
  review_required: boolean;
}

export interface SignalCalibrationDashboardRow {
  target_key: string;
  signal_type: string;
  category: string;
  regime: string;
  source: "active_calibration" | "candidate_from_tracks" | string;
  sample_size: number;
  hit_count: number;
  miss_count: number;
  rolling_hit_rate: number | null;
  posterior_mean: number;
  confidence_low: number;
  confidence_high: number;
  base_weight: number;
  effective_weight: number;
  alpha_prior: number;
  beta_prior: number;
  prior_dominant: boolean;
  decay_detected: boolean;
  computed_at: string | null;
  effective_from: string | null;
}

export interface SignalCalibrationDashboard {
  generated_at: string;
  lookback_days: number;
  confidence_level: number;
  total_buckets: number;
  mature_buckets: number;
  prior_dominant_buckets: number;
  decay_buckets: number;
  sample_size: number;
  avg_effective_weight: number | null;
  rows: SignalCalibrationDashboardRow[];
  notes: string[];
}

export interface DriftMetric {
  id: string;
  metric_type: string;
  category: string | null;
  feature_name: string | null;
  current_value: number | null;
  baseline_value: number | null;
  psi: number | null;
  drift_severity: "green" | "yellow" | "red" | string;
  details: Record<string, unknown>;
  computed_at: string;
}

export interface DriftNotification {
  level: "none" | "watch" | "review" | "no_data" | string;
  title: string;
  summary: string;
  should_notify: boolean;
  production_effect: "observe_only" | string;
  channels: string[];
  next_actions: string[];
  top_metrics: DriftMetric[];
}

export interface DriftSnapshot {
  generated_at: string;
  latest_at: string | null;
  status: "green" | "yellow" | "red" | "no_data" | string;
  severity_counts: Record<string, number>;
  notification: DriftNotification;
  metrics: DriftMetric[];
}

export interface LearningHypothesis {
  id: string;
  hypothesis: string;
  supporting_evidence: string[];
  proposed_change: string | null;
  confidence: number;
  sample_size: number;
  counterevidence: string[];
  status: string;
  evidence_strength: string;
  rejection_reason: string | null;
  created_at: string | null;
}

export interface NotebookReference {
  id: string;
  type: "alert" | "hypothesis" | "report";
  title: string;
  status: string | null;
  timestamp: string | null;
  relation: string;
}

export interface NotebookEntry {
  id: string;
  kind: "report" | "learning_hypothesis" | "research_hypothesis";
  title: string;
  summary: string;
  body: string;
  status: string;
  confidence: number | null;
  folder: string;
  tags: string[];
  symbols: string[];
  references: NotebookReference[];
  createdAt: string;
  updatedAt: string | null;
}

export interface NotebookFolder {
  name: string;
  count: number;
}

export interface NotebookSnapshot {
  generatedAt: string;
  source: "database";
  notes: NotebookEntry[];
  folders: NotebookFolder[];
  referenceCounts: Record<string, number>;
}

export interface NewsEvent {
  id: string;
  source: string;
  rawUrl?: string | null;
  title: string;
  titleOriginal?: string | null;
  titleZh?: string | null;
  summary: string;
  summaryOriginal?: string | null;
  summaryZh?: string | null;
  sourceLanguage?: string;
  translationStatus?: string;
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

export type EventIntelligenceStatus = "shadow_review" | "human_review" | "confirmed" | "rejected";
export type EventImpactDirection = "bullish" | "bearish" | "mixed" | "watch";
export type EventIntelligenceDecision = "confirm" | "reject" | "request_review" | "shadow_review";
export type EventIntelligenceQualityStatus = "blocked" | "review" | "shadow_ready" | "decision_grade";
export type EventImpactLinkQualityStatus = "blocked" | "review" | "passed";
export type EventIntelligenceQualitySeverity = "blocker" | "warning" | "info";
export type GovernanceReviewStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "reviewed"
  | "shadow_review";
export type GovernanceReviewDecision = "approve" | "reject" | "mark_reviewed" | "shadow_review";

export interface EventIntelligenceItem {
  id: string;
  sourceType: string;
  sourceId: string | null;
  title: string;
  summary: string;
  eventType: string;
  eventTimestamp: string;
  entities: string[];
  symbols: string[];
  regions: string[];
  mechanisms: string[];
  evidence: string[];
  counterevidence: string[];
  confidence: number;
  impactScore: number;
  status: EventIntelligenceStatus;
  requiresManualConfirmation: boolean;
  sourceReliability: number;
  freshnessScore: number;
  sourcePayload: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface EventImpactLink {
  id: string;
  eventItemId: string;
  symbol: string;
  regionId: string | null;
  mechanism: string;
  direction: EventImpactDirection;
  confidence: number;
  impactScore: number;
  horizon: string;
  rationale: string;
  evidence: string[];
  counterevidence: string[];
  status: EventIntelligenceStatus;
  createdAt: string;
  updatedAt: string;
}

export interface EventImpactLinkUpdateInput {
  symbol?: string | null;
  regionId?: string | null;
  mechanism?: string | null;
  direction?: EventImpactDirection | null;
  confidence?: number | null;
  impactScore?: number | null;
  horizon?: string | null;
  rationale?: string | null;
  evidence?: string[] | null;
  counterevidence?: string[] | null;
  note?: string | null;
}

export interface EventIntelligenceAuditLog {
  id: string;
  eventItemId: string;
  action: string;
  actor: string | null;
  beforeStatus: string | null;
  afterStatus: string | null;
  note: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface EventIntelligenceDecisionResult {
  event: EventIntelligenceItem;
  auditLog: EventIntelligenceAuditLog;
}

export interface EventIntelligenceResolveResult {
  event: EventIntelligenceItem;
  impactLinks: EventImpactLink[];
  created: boolean;
}

export interface EventImpactLinkUpdateResult {
  event: EventIntelligenceItem;
  impactLink: EventImpactLink;
  auditLog: EventIntelligenceAuditLog;
}

export interface EventIntelligenceQualityIssue {
  code: string;
  severity: EventIntelligenceQualitySeverity;
  message: string;
}

export interface EventImpactLinkQuality {
  id: string;
  symbol: string;
  mechanism: string;
  score: number;
  status: EventImpactLinkQualityStatus;
  passedGate: boolean;
  issues: EventIntelligenceQualityIssue[];
}

export interface EventIntelligenceQualityReport {
  eventId: string;
  score: number;
  status: EventIntelligenceQualityStatus;
  passedGate: boolean;
  decisionGrade: boolean;
  issues: EventIntelligenceQualityIssue[];
  linkReports: EventImpactLinkQuality[];
}

export interface EventIntelligenceQualitySummary {
  generatedAt: string;
  total: number;
  averageScore: number;
  blocked: number;
  review: number;
  shadowReady: number;
  decisionGrade: number;
  reports: EventIntelligenceQualityReport[];
}

export interface GovernanceReview {
  id: string;
  source: string;
  targetTable: string;
  targetKey: string;
  proposedChange: Record<string, unknown>;
  status: GovernanceReviewStatus | string;
  reason: string | null;
  reviewedBy: string | null;
  reviewedAt: string | null;
  createdAt: string;
}

interface BackendAlert {
  id: string;
  title: string;
  summary: string;
  title_original?: string | null;
  summary_original?: string | null;
  title_zh?: string | null;
  summary_zh?: string | null;
  source_language?: string;
  translation_status?: string;
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
  title_original?: string | null;
  summary_original?: string | null;
  title_zh?: string | null;
  summary_zh?: string | null;
  source_language?: string;
  translation_status?: string;
  translation_model?: string | null;
  translation_prompt_version?: string | null;
  translation_glossary_version?: string | null;
  translated_at?: string | null;
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

interface BackendEventIntelligenceItem {
  id: string;
  source_type: string;
  source_id: string | null;
  title: string;
  summary: string;
  event_type: string;
  event_timestamp: string;
  entities: string[];
  symbols: string[];
  regions: string[];
  mechanisms: string[];
  evidence: string[];
  counterevidence: string[];
  confidence: number;
  impact_score: number;
  status: EventIntelligenceStatus;
  requires_manual_confirmation: boolean;
  source_reliability: number;
  freshness_score: number;
  source_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface BackendEventImpactLink {
  id: string;
  event_item_id: string;
  symbol: string;
  region_id: string | null;
  mechanism: string;
  direction: EventImpactDirection;
  confidence: number;
  impact_score: number;
  horizon: string;
  rationale: string;
  evidence: string[];
  counterevidence: string[];
  status: EventIntelligenceStatus;
  created_at: string;
  updated_at: string;
}

interface BackendEventIntelligenceAuditLog {
  id: string;
  event_item_id: string;
  action: string;
  actor: string | null;
  before_status: string | null;
  after_status: string | null;
  note: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

interface BackendEventIntelligenceDecisionResponse {
  event: BackendEventIntelligenceItem;
  audit_log: BackendEventIntelligenceAuditLog;
}

interface BackendEventImpactLinkUpdateResponse {
  event: BackendEventIntelligenceItem;
  impact_link: BackendEventImpactLink;
  audit_log: BackendEventIntelligenceAuditLog;
}

interface BackendEventIntelligenceResolveResponse {
  event: BackendEventIntelligenceItem;
  impact_links: BackendEventImpactLink[];
  created: boolean;
}

interface BackendEventIntelligenceQualityIssue {
  code: string;
  severity: EventIntelligenceQualitySeverity;
  message: string;
}

interface BackendEventImpactLinkQuality {
  id: string;
  symbol: string;
  mechanism: string;
  score: number;
  status: EventImpactLinkQualityStatus;
  passed_gate: boolean;
  issues: BackendEventIntelligenceQualityIssue[];
}

interface BackendEventIntelligenceQualityReport {
  event_id: string;
  score: number;
  status: EventIntelligenceQualityStatus;
  passed_gate: boolean;
  decision_grade: boolean;
  issues: BackendEventIntelligenceQualityIssue[];
  link_reports: BackendEventImpactLinkQuality[];
}

interface BackendEventIntelligenceQualitySummary {
  generated_at: string;
  total: number;
  average_score: number;
  blocked: number;
  review: number;
  shadow_ready: number;
  decision_grade: number;
  reports: BackendEventIntelligenceQualityReport[];
}

interface BackendGovernanceReview {
  id: string;
  source: string;
  target_table: string;
  target_key: string;
  proposed_change: Record<string, unknown>;
  status: GovernanceReviewStatus | string;
  reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

interface BackendNotebookEntry {
  id: string;
  kind: "report" | "learning_hypothesis" | "research_hypothesis";
  title: string;
  summary: string;
  body: string;
  status: string;
  confidence: number | null;
  folder: string;
  tags: string[];
  symbols: string[];
  references: NotebookReference[];
  created_at: string;
  updated_at: string | null;
}

interface BackendNotebookSnapshot {
  generated_at: string;
  source: "database";
  notes: BackendNotebookEntry[];
  folders: NotebookFolder[];
  reference_counts: Record<string, number>;
}

interface BackendRecommendation {
  id: string;
  alert_id?: string | null;
  status: string;
  recommended_action: string;
  legs: BackendLeg[];
  priority_score: number;
  portfolio_fit_score: number;
  margin_efficiency_score: number;
  margin_required: number;
  reasoning: string;
  one_liner?: string | null;
  risk_items: string[];
  expires_at: string;
  created_at: string;
  position_size_pct?: number | null;
  risk_reward_ratio?: number | null;
  backtest_summary?: Record<string, unknown> | null;
  entry_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
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
  degraded?: boolean;
  unavailable_sections?: string[];
}

export async function fetchAlertsFromApi(): Promise<Alert[]> {
  const alerts = await fetchJson<BackendAlert[]>("/api/alerts?limit=100");
  return alerts.map(mapAlert);
}

export async function fetchPortfolioSnapshot(): Promise<PortfolioSnapshot> {
  const unavailableSections: string[] = [];
  const [positionsResult, varResult, stressResult] = await Promise.allSettled([
    fetchJson<BackendPosition[]>("/api/positions?status_filter=open&limit=500"),
    fetchJson<ApiEnvelope<RiskVarResult>>("/api/risk/var"),
    fetchJson<ApiEnvelope<StressTestResult[]>>("/api/risk/stress"),
  ]);
  if (positionsResult.status === "rejected") {
    throw positionsResult.reason;
  }

  const positions = positionsResult.value;
  const varEnvelope = optionalSettledValue(varResult, null, "var", unavailableSections);
  const stressEnvelope = optionalSettledValue(stressResult, null, "stress", unavailableSections);
  appendEnvelopeSections(varEnvelope, "var", unavailableSections);
  appendEnvelopeSections(stressEnvelope, "stress", unavailableSections);
  const symbols = uniqueSymbols(positions);
  const latestRows = await fetchLatestMarketRows(symbols);
  const mappedPositions = positions.map((position) => mapPosition(position, latestRows));

  const correlation =
    symbols.length > 0
      ? await fetchOptionalEnvelope<CorrelationMatrix>(
          `/api/risk/correlation?symbols=${encodeURIComponent(symbols.join(","))}&window=60`,
          "correlation",
          unavailableSections
        )
      : null;

  return {
    positions: mappedPositions,
    varResult: varEnvelope?.data ?? null,
    stressResults: stressEnvelope?.data ?? [],
    correlation,
    degraded: unavailableSections.length > 0,
    unavailableSections,
  };
}

export async function fetchSectorSnapshot(baseSectors: SectorData[]): Promise<SectorSnapshot> {
  const unavailableSections: string[] = [];
  const [alertsResult, marketResult] = await Promise.allSettled([
    fetchAlertsFromApi(),
    fetchSectorMarketChanges(baseSectors),
  ]);
  const alerts = optionalSettledValue(alertsResult, null, "alerts", unavailableSections);
  const market = optionalSettledValue(marketResult, null, "market", unavailableSections);

  if (alerts === null && market === null) {
    throw new Error("sector snapshot sources unavailable");
  }

  if (market?.missingSymbols.length) {
    unavailableSections.push(`market:${market.missingSymbols.join(",")}`);
  }

  const activeSymbols = alerts
    ? new Set(alerts.flatMap((alert) => rootSymbols([alert.symbol, ...alert.signalChain])))
    : null;

  const sectors = baseSectors.map((sector) => {
    const symbols = sector.symbols.map((symbol) => {
      const change = market?.changes.get(symbol.code) ?? 0;
      return {
        ...symbol,
        change,
        signalActive: activeSymbols ? activeSymbols.has(symbol.code) : false,
      };
    });
    const avgChange =
      symbols.reduce((total, symbol) => total + symbol.change, 0) / Math.max(symbols.length, 1);
    return {
      ...sector,
      conviction: market ? clamp(avgChange / 2.5, -1, 1) : 0,
      symbols,
    };
  });

  return {
    sectors,
    degraded: unavailableSections.length > 0,
    unavailableSections,
  };
}

export async function fetchNewsEventsFromApi(): Promise<NewsEvent[]> {
  const rows = await fetchJson<BackendNewsEvent[]>("/api/news-events?limit=200");
  return rows.map(mapNewsEvent);
}

export async function fetchEventIntelligenceItems(limit = 100): Promise<EventIntelligenceItem[]> {
  const rows = await fetchJson<BackendEventIntelligenceItem[]>(
    `/api/event-intelligence?limit=${limit}`
  );
  return rows.map(mapEventIntelligenceItem);
}

export async function fetchEventImpactLinks(params: {
  symbol?: string;
  regionId?: string;
  mechanism?: string;
  status?: EventIntelligenceStatus;
  limit?: number;
} = {}): Promise<EventImpactLink[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 200));
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.regionId) query.set("region_id", params.regionId);
  if (params.mechanism) query.set("mechanism", params.mechanism);
  if (params.status) query.set("status", params.status);
  const rows = await fetchJson<BackendEventImpactLink[]>(
    `/api/event-intelligence/impact-links?${query.toString()}`
  );
  return rows.map(mapEventImpactLink);
}

export async function fetchEventIntelligenceQualitySummary(limit = 200): Promise<EventIntelligenceQualitySummary> {
  const row = await fetchJson<BackendEventIntelligenceQualitySummary>(
    `/api/event-intelligence/quality?limit=${limit}`
  );
  return mapEventIntelligenceQualitySummary(row);
}

export async function fetchEventIntelligenceAuditLogs(params: {
  eventItemId?: string;
  action?: string;
  limit?: number;
} = {}): Promise<EventIntelligenceAuditLog[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 50));
  if (params.eventItemId) query.set("event_item_id", params.eventItemId);
  if (params.action) query.set("action", params.action);
  const rows = await fetchJson<BackendEventIntelligenceAuditLog[]>(
    `/api/event-intelligence/audit-logs?${query.toString()}`
  );
  return rows.map(mapEventIntelligenceAuditLog);
}

export async function fetchGovernanceReviews(params: {
  status?: GovernanceReviewStatus | "all";
  source?: string;
  targetTable?: string;
  limit?: number;
} = {}): Promise<GovernanceReview[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 200));
  if (params.status && params.status !== "all") query.set("status", params.status);
  if (params.source) query.set("source", params.source);
  if (params.targetTable) query.set("target_table", params.targetTable);
  const rows = await fetchJson<BackendGovernanceReview[]>(
    `/api/governance/reviews?${query.toString()}`
  );
  return rows.map(mapGovernanceReview);
}

export async function decideGovernanceReview(
  reviewId: string,
  decision: GovernanceReviewDecision,
  note?: string
): Promise<GovernanceReview> {
  const row = await fetchJson<BackendGovernanceReview>(
    `/api/governance/reviews/${encodeURIComponent(reviewId)}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        reviewed_by: "zeus-ui",
        note,
      }),
    }
  );
  return mapGovernanceReview(row);
}

export async function createEventIntelligenceFromNews(
  newsEventId: string
): Promise<EventIntelligenceResolveResult> {
  const row = await fetchJson<BackendEventIntelligenceResolveResponse>(
    `/api/event-intelligence/from-news/${encodeURIComponent(newsEventId)}`,
    { method: "POST" }
  );
  return {
    event: mapEventIntelligenceItem(row.event),
    impactLinks: row.impact_links.map(mapEventImpactLink),
    created: row.created,
  };
}

export async function fetchEventIntelligenceDetail(
  eventId: string
): Promise<EventIntelligenceResolveResult> {
  const row = await fetchJson<BackendEventIntelligenceResolveResponse>(
    `/api/event-intelligence/${encodeURIComponent(eventId)}`
  );
  return {
    event: mapEventIntelligenceItem(row.event),
    impactLinks: row.impact_links.map(mapEventImpactLink),
    created: row.created,
  };
}

export async function decideEventIntelligence(
  eventId: string,
  decision: EventIntelligenceDecision,
  note?: string
): Promise<EventIntelligenceDecisionResult> {
  const row = await fetchJson<BackendEventIntelligenceDecisionResponse>(
    `/api/event-intelligence/${eventId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        decided_by: "zeus-ui",
        note,
      }),
    }
  );
  return {
    event: mapEventIntelligenceItem(row.event),
    auditLog: mapEventIntelligenceAuditLog(row.audit_log),
  };
}

export async function updateEventImpactLink(
  linkId: string,
  payload: EventImpactLinkUpdateInput
): Promise<EventImpactLinkUpdateResult> {
  const row = await fetchJson<BackendEventImpactLinkUpdateResponse>(
    `/api/event-intelligence/impact-links/${encodeURIComponent(linkId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: payload.symbol,
        region_id: payload.regionId,
        mechanism: payload.mechanism,
        direction: payload.direction,
        confidence: payload.confidence,
        impact_score: payload.impactScore,
        horizon: payload.horizon,
        rationale: payload.rationale,
        evidence: payload.evidence,
        counterevidence: payload.counterevidence,
        edited_by: "zeus-ui",
        note: payload.note,
      }),
    }
  );
  return {
    event: mapEventIntelligenceItem(row.event),
    impactLink: mapEventImpactLink(row.impact_link),
    auditLog: mapEventIntelligenceAuditLog(row.audit_log),
  };
}

export async function fetchTradePlansFromApi(): Promise<TradePlan[]> {
  const rows = await fetchJson<BackendRecommendation[]>("/api/recommendations?limit=200");
  const visibleRows = rows.filter(
    (row) => isVisibleTradePlanStatus(row.status) && isUnexpiredRecommendation(row)
  );
  const symbols = Array.from(
    new Set(
      visibleRows
        .map((row) => recommendationSymbol(row))
        .filter((symbol): symbol is string => symbol !== null)
    )
  );
  const latestRows = await fetchLatestMarketRows(symbols);
  return visibleRows
    .map((row) => mapTradePlan(row, latestRows))
    .filter((plan): plan is TradePlan => plan !== null);
}

export async function fetchCausalWebGraph(params?: {
  limit?: number;
  symbol?: string | null;
  region?: string | null;
  event?: string | null;
}): Promise<CausalWebGraph> {
  const query = new URLSearchParams({ limit: String(params?.limit ?? 10) });
  if (params?.symbol) query.set("symbol", params.symbol);
  if (params?.region) query.set("region", params.region);
  if (params?.event) query.set("event", params.event);
  return fetchJson<CausalWebGraph>(`/api/causal-web?${query.toString()}`);
}

export interface WorldMapFilterParams {
  symbol?: string;
  mechanism?: string;
  source?: string;
  viewport?: WorldMapViewport;
}

export interface WorldMapViewport {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

function worldMapQuery(params?: WorldMapFilterParams): string {
  const query = new URLSearchParams();
  if (params?.symbol) query.set("symbol", params.symbol);
  if (params?.mechanism) query.set("mechanism", params.mechanism);
  if (params?.source) query.set("source", params.source);
  if (params?.viewport) {
    query.set("min_lat", params.viewport.minLat.toFixed(4));
    query.set("max_lat", params.viewport.maxLat.toFixed(4));
    query.set("min_lon", params.viewport.minLon.toFixed(4));
    query.set("max_lon", params.viewport.maxLon.toFixed(4));
  }
  const value = query.toString();
  return value ? `?${value}` : "";
}

export async function fetchWorldMapSnapshot(params?: WorldMapFilterParams): Promise<WorldMapSnapshot> {
  return fetchJson<WorldMapSnapshot>(`/api/world-map${worldMapQuery(params)}`);
}

export async function fetchWorldMapTiles(
  layer: WorldMapTileLayerFilter = "all",
  resolution: WorldMapTileResolution = "coarse",
  filters?: WorldMapFilterParams
): Promise<WorldMapTileSnapshot> {
  const query = new URLSearchParams({ layer, resolution });
  if (filters?.symbol) query.set("symbol", filters.symbol);
  if (filters?.mechanism) query.set("mechanism", filters.mechanism);
  if (filters?.source) query.set("source", filters.source);
  if (filters?.viewport) {
    query.set("min_lat", filters.viewport.minLat.toFixed(4));
    query.set("max_lat", filters.viewport.maxLat.toFixed(4));
    query.set("min_lon", filters.viewport.minLon.toFixed(4));
    query.set("max_lon", filters.viewport.maxLon.toFixed(4));
  }
  return fetchJson<WorldMapTileSnapshot>(`/api/world-map/tiles?${query.toString()}`);
}

export async function fetchDataSourceStatuses(): Promise<DataSourceStatus[]> {
  return fetchJson<DataSourceStatus[]>("/api/data-sources");
}

export async function fetchContracts(limit = 500): Promise<ContractMetadata[]> {
  return fetchJson<ContractMetadata[]>(`/api/contracts?limit=${limit}`);
}

export async function fetchSchedulerSnapshot(): Promise<SchedulerSnapshot> {
  return fetchJson<SchedulerSnapshot>("/api/scheduler");
}

export async function fetchLLMUsageSummary(module = "alert_agent"): Promise<LLMUsageSummary> {
  const params = new URLSearchParams({ module });
  return fetchJson<LLMUsageSummary>(`/api/llm/usage?${params.toString()}`);
}

export async function fetchLLMProviderSettings(): Promise<LLMProviderSettings[]> {
  return fetchJson<LLMProviderSettings[]>("/api/settings/llm-providers");
}

export async function fetchAlertDedupSettings(): Promise<AlertDedupSettings> {
  return fetchJson<AlertDedupSettings>("/api/settings/alert-dedup");
}

export async function fetchNotificationSettings(): Promise<NotificationSettings> {
  return fetchJson<NotificationSettings>("/api/settings/notifications");
}

export async function updateNotificationSettings(
  payload: NotificationSettingsUpdate,
): Promise<NotificationSettings> {
  return fetchJson<NotificationSettings>("/api/settings/notifications", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchAdversarialRuntimeSettings(): Promise<AdversarialRuntimeSettings> {
  return fetchJson<AdversarialRuntimeSettings>("/api/settings/adversarial-runtime");
}

export async function updateAdversarialRuntimeSettings(
  payload: AdversarialRuntimeSettingsUpdate,
): Promise<AdversarialRuntimeSettings> {
  return fetchJson<AdversarialRuntimeSettings>("/api/settings/adversarial-runtime", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchAttributionReport(): Promise<AttributionReport> {
  return fetchJson<AttributionReport>("/api/attribution/report");
}

export async function fetchCostChain(symbol = "RB"): Promise<CostChain> {
  return fetchJson<CostChain>(`/api/cost-models/${encodeURIComponent(symbol)}/chain`);
}

export async function fetchCostHistory(symbol: string, limit = 30): Promise<CostSnapshot[]> {
  return fetchJson<CostSnapshot[]>(
    `/api/cost-models/${encodeURIComponent(symbol)}/history?limit=${limit}`
  );
}

export async function fetchCostHistories(
  symbols: readonly string[],
  limit = 30
): Promise<Record<string, CostSnapshot[]>> {
  const uniqueSymbols = Array.from(
    new Set(symbols.map((symbol) => symbol.trim()).filter((symbol) => symbol.length > 0))
  ).sort();
  if (uniqueSymbols.length === 0) {
    return {};
  }
  return fetchJson<Record<string, CostSnapshot[]>>(
    `/api/cost-models/histories?symbols=${encodeURIComponent(uniqueSymbols.join(","))}&limit=${limit}`
  );
}

export async function simulateCostModel(
  symbol: string,
  payload: CostSimulationRequest
): Promise<CostModel> {
  return fetchJson<CostModel>(`/api/cost-models/${encodeURIComponent(symbol)}/simulate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchCostQualityReport(
  sector: "ferrous" | "rubber" = "ferrous"
): Promise<CostQualityReport> {
  return fetchJson<CostQualityReport>(`/api/cost-models/quality/${sector}`);
}

export async function runScenarioSimulation(
  payload: ScenarioSimulationRequest
): Promise<ScenarioReport> {
  return fetchJson<ScenarioReport>("/api/scenarios/simulate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchBacktestQualitySummary(): Promise<BacktestQualitySummary> {
  return fetchJson<BacktestQualitySummary>("/api/strategies/backtest-quality");
}

export async function fetchThresholdCalibrationReport(): Promise<ThresholdCalibrationReport> {
  return fetchJson<ThresholdCalibrationReport>("/api/shadow/calibration");
}

export async function fetchSignalCalibrationDashboard(): Promise<SignalCalibrationDashboard> {
  return fetchJson<SignalCalibrationDashboard>("/api/calibration/dashboard");
}

export async function fetchDriftSnapshot(): Promise<DriftSnapshot> {
  return fetchJson<DriftSnapshot>("/api/drift/metrics?limit=100");
}

export async function fetchLearningHypotheses(): Promise<LearningHypothesis[]> {
  return fetchJson<LearningHypothesis[]>("/api/learning/hypotheses");
}

export async function fetchNotebookSnapshot(): Promise<NotebookSnapshot> {
  const snapshot = await fetchJson<BackendNotebookSnapshot>("/api/notebook?limit=100");
  return {
    generatedAt: snapshot.generated_at,
    source: snapshot.source,
    notes: snapshot.notes.map((note) => ({
      id: note.id,
      kind: note.kind,
      title: note.title,
      summary: note.summary,
      body: note.body,
      status: note.status,
      confidence: note.confidence,
      folder: note.folder,
      tags: note.tags,
      symbols: note.symbols,
      references: note.references,
      createdAt: note.created_at,
      updatedAt: note.updated_at,
    })),
    folders: snapshot.folders,
    referenceCounts: snapshot.reference_counts,
  };
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

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const signal = init.signal ?? controller.signal;
  const timeoutId = init.signal
    ? null
    : window.setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS);

  try {
    const response = await fetch(path, { cache: "no-store", ...init, signal });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(path, response));
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`${path} timed out after ${DEFAULT_API_TIMEOUT_MS / 1000}s`);
    }
    throw error;
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}

async function apiErrorMessage(path: string, response: Response): Promise<string> {
  try {
    const payload = (await response.clone().json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return `${path} failed with ${response.status}: ${payload.detail}`;
    }
  } catch {
    // Keep the generic status message when the backend did not return JSON.
  }
  return `${path} failed with ${response.status}`;
}

function optionalSettledValue<T>(
  result: PromiseSettledResult<T>,
  fallback: T | null,
  section: string,
  unavailableSections: string[]
): T | null {
  if (result.status === "fulfilled") {
    return result.value;
  }
  unavailableSections.push(section);
  return fallback;
}

async function fetchOptionalEnvelope<T>(
  path: string,
  section: string,
  unavailableSections: string[]
): Promise<T | null> {
  try {
    const envelope = await fetchJson<ApiEnvelope<T>>(path);
    appendEnvelopeSections(envelope, section, unavailableSections);
    return envelope.data;
  } catch {
    unavailableSections.push(section);
    return null;
  }
}

function appendEnvelopeSections<T>(
  envelope: ApiEnvelope<T> | null,
  section: string,
  unavailableSections: string[]
): void {
  if (!envelope?.degraded) {
    return;
  }
  const reasons = envelope.unavailable_sections?.length
    ? envelope.unavailable_sections
    : ["degraded"];
  reasons.forEach((reason) => unavailableSections.push(`${section}:${reason}`));
}

async function fetchLatestMarketRows(symbols: string[]): Promise<Map<string, BackendMarketData>> {
  const uniqueSymbols = Array.from(
    new Set(symbols.map((symbol) => symbol.trim()).filter((symbol) => symbol.length > 0))
  ).sort();
  if (uniqueSymbols.length === 0) {
    return new Map();
  }

  try {
    const rows = await fetchJson<BackendMarketData[]>(
      `/api/market-data/latest?symbols=${encodeURIComponent(uniqueSymbols.join(","))}`
    );
    return new Map(rows.map((row) => [row.symbol, row]));
  } catch {
    // Older or partially degraded backends can still serve per-symbol latest rows.
  }

  const entries = await Promise.all(
    uniqueSymbols.map(async (symbol) => {
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

async function fetchSectorMarketChanges(baseSectors: SectorData[]): Promise<{
  changes: Map<string, number>;
  missingSymbols: string[];
}> {
  const symbols = Array.from(
    new Set(baseSectors.flatMap((sector) => sector.symbols.map((symbol) => symbol.code)))
  ).sort();
  if (symbols.length === 0) {
    return { changes: new Map(), missingSymbols: [] };
  }

  try {
    const rows = await fetchJson<BackendMarketData[]>(
      `/api/market-data/recent?symbols=${encodeURIComponent(symbols.join(","))}&limit=5`
    );
    return changesFromMarketRows(symbols, rows);
  } catch {
    // Fall back to the older per-symbol endpoint if the batch endpoint is unavailable.
  }

  const entries = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const rows = await fetchJson<BackendMarketData[]>(
          `/api/market-data?symbol=${encodeURIComponent(symbol)}&limit=5`
        );
        return [symbol, marketChangePct(rows)] as const;
      } catch {
        return [symbol, null] as const;
      }
    })
  );
  const changes = new Map<string, number>();
  const missingSymbols: string[] = [];
  for (const [symbol, change] of entries) {
    if (change === null) {
      missingSymbols.push(symbol);
    } else {
      changes.set(symbol, change);
    }
  }
  return { changes, missingSymbols };
}

function changesFromMarketRows(
  symbols: string[],
  rows: BackendMarketData[]
): { changes: Map<string, number>; missingSymbols: string[] } {
  const rowsBySymbol = new Map<string, BackendMarketData[]>();
  rows.forEach((row) => {
    const symbolRows = rowsBySymbol.get(row.symbol) ?? [];
    symbolRows.push(row);
    rowsBySymbol.set(row.symbol, symbolRows);
  });

  const changes = new Map<string, number>();
  const missingSymbols: string[] = [];
  symbols.forEach((symbol) => {
    const change = marketChangePct(rowsBySymbol.get(symbol) ?? []);
    if (change === null) {
      missingSymbols.push(symbol);
    } else {
      changes.set(symbol, change);
    }
  });
  return { changes, missingSymbols };
}

function marketChangePct(rows: BackendMarketData[]): number | null {
  const latest = rows[0];
  if (!latest) return null;
  const previous =
    rows.find((row) => row.timestamp !== latest.timestamp && row.close > 0) ??
    rows.find((row) => row.close > 0 && row.close !== latest.close);
  if (!previous || previous.close === 0) return null;
  return ((latest.close - previous.close) / previous.close) * 100;
}

function mapNewsEvent(event: BackendNewsEvent): NewsEvent {
  const title = preferredText(event.title_zh, event.title);
  const summary = preferredText(event.summary_zh, event.summary);
  return {
    id: event.id,
    source: event.source,
    rawUrl: event.raw_url,
    title,
    titleOriginal: event.title_original ?? event.title,
    titleZh: event.title_zh,
    summary,
    summaryOriginal: event.summary_original ?? event.summary,
    summaryZh: event.summary_zh,
    sourceLanguage: event.source_language,
    translationStatus: event.translation_status,
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

function preferredText(translated: string | null | undefined, fallback: string): string {
  const text = translated?.trim();
  return text || fallback;
}

function mapEventIntelligenceItem(event: BackendEventIntelligenceItem): EventIntelligenceItem {
  return {
    id: event.id,
    sourceType: event.source_type,
    sourceId: event.source_id,
    title: event.title,
    summary: event.summary,
    eventType: event.event_type,
    eventTimestamp: event.event_timestamp,
    entities: event.entities,
    symbols: event.symbols,
    regions: event.regions,
    mechanisms: event.mechanisms,
    evidence: event.evidence,
    counterevidence: event.counterevidence,
    confidence: event.confidence,
    impactScore: event.impact_score,
    status: event.status,
    requiresManualConfirmation: event.requires_manual_confirmation,
    sourceReliability: event.source_reliability,
    freshnessScore: event.freshness_score,
    sourcePayload: event.source_payload,
    createdAt: event.created_at,
    updatedAt: event.updated_at,
  };
}

function mapEventImpactLink(link: BackendEventImpactLink): EventImpactLink {
  return {
    id: link.id,
    eventItemId: link.event_item_id,
    symbol: link.symbol,
    regionId: link.region_id,
    mechanism: link.mechanism,
    direction: link.direction,
    confidence: link.confidence,
    impactScore: link.impact_score,
    horizon: link.horizon,
    rationale: link.rationale,
    evidence: link.evidence,
    counterevidence: link.counterevidence,
    status: link.status,
    createdAt: link.created_at,
    updatedAt: link.updated_at,
  };
}

function mapEventIntelligenceAuditLog(
  auditLog: BackendEventIntelligenceAuditLog
): EventIntelligenceAuditLog {
  return {
    id: auditLog.id,
    eventItemId: auditLog.event_item_id,
    action: auditLog.action,
    actor: auditLog.actor,
    beforeStatus: auditLog.before_status,
    afterStatus: auditLog.after_status,
    note: auditLog.note,
    payload: auditLog.payload,
    createdAt: auditLog.created_at,
  };
}

function mapGovernanceReview(review: BackendGovernanceReview): GovernanceReview {
  return {
    id: review.id,
    source: review.source,
    targetTable: review.target_table,
    targetKey: review.target_key,
    proposedChange: review.proposed_change,
    status: review.status,
    reason: review.reason,
    reviewedBy: review.reviewed_by,
    reviewedAt: review.reviewed_at,
    createdAt: review.created_at,
  };
}

function mapEventIntelligenceQualitySummary(
  summary: BackendEventIntelligenceQualitySummary
): EventIntelligenceQualitySummary {
  return {
    generatedAt: summary.generated_at,
    total: summary.total,
    averageScore: summary.average_score,
    blocked: summary.blocked,
    review: summary.review,
    shadowReady: summary.shadow_ready,
    decisionGrade: summary.decision_grade,
    reports: summary.reports.map((report) => ({
      eventId: report.event_id,
      score: report.score,
      status: report.status,
      passedGate: report.passed_gate,
      decisionGrade: report.decision_grade,
      issues: report.issues,
      linkReports: report.link_reports.map((link) => ({
        id: link.id,
        symbol: link.symbol,
        mechanism: link.mechanism,
        score: link.score,
        status: link.status,
        passedGate: link.passed_gate,
        issues: link.issues,
      })),
    })),
  };
}

function mapTradePlan(
  recommendation: BackendRecommendation,
  latestRows: Map<string, BackendMarketData>
): TradePlan | null {
  const symbol = recommendationSymbol(recommendation);
  const direction = recommendationDirection(recommendation);
  if (symbol === null || direction === null) {
    return null;
  }

  const leg = primaryRecommendationLeg(recommendation);
  const latest = latestRows.get(symbol);
  const currentPrice = positiveNumber(
    latest?.close,
    leg.currentPrice,
    leg.current_price,
    leg.price,
    recommendation.entry_price
  );
  const entryPrice =
    positiveNumber(
      recommendation.entry_price,
      leg.entryPrice,
      leg.entry_price,
      leg.avgEntry,
      currentPrice
    ) ?? 1;
  const stopLoss =
    positiveNumber(recommendation.stop_loss) ?? inferredStopLoss(entryPrice, direction);
  const takeProfit =
    positiveNumber(recommendation.take_profit) ??
    inferredTakeProfit(entryPrice, direction, recommendation.risk_reward_ratio);
  const riskPercent = riskPercentFromPlan(entryPrice, stopLoss, direction);
  const rewardPercent = rewardPercentFromPlan(entryPrice, takeProfit, direction);
  const riskReward =
    recommendation.risk_reward_ratio ??
    (riskPercent !== 0 ? Math.abs(rewardPercent / riskPercent) : 0);

  return {
    id: recommendation.id,
    alertId: recommendation.alert_id ?? recommendation.id,
    status: recommendation.status,
    reviewRequired: recommendation.status !== "pending",
    symbol,
    symbolName: symbol,
    direction,
    size: positiveNumber(leg.lots, leg.size, leg.quantity, recommendation.position_size_pct) ?? 1,
    entryPrice,
    stopLoss,
    takeProfit,
    currentPrice: currentPrice ?? entryPrice,
    riskPercent,
    rewardPercent,
    riskReward,
    marginUsage: normalizedMarginUsage(recommendation.margin_required),
    portfolioRisk: normalizedPortfolioRisk(recommendation.portfolio_fit_score),
    signalSummary:
      recommendation.one_liner ||
      recommendation.reasoning ||
      recommendation.risk_items.join(" · ") ||
      recommendation.recommended_action,
    confidence: normalizedScore(recommendation.priority_score),
    sampleSize: sampleSizeFromBacktestSummary(recommendation.backtest_summary),
    createdAt: recommendation.created_at,
  };
}

function isVisibleTradePlanStatus(status: string): boolean {
  return status === "pending" || status === "pending_review";
}

function isUnexpiredRecommendation(recommendation: BackendRecommendation): boolean {
  return new Date(recommendation.expires_at).getTime() > Date.now();
}

function sampleSizeFromBacktestSummary(summary: Record<string, unknown> | null | undefined): number {
  if (!summary) return 0;
  const candidates = [
    summary.sample_size,
    summary.sampleSize,
    summary.samples,
    summary.total_samples,
    summary.n,
  ];
  for (const value of candidates) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed >= 0) return Math.floor(parsed);
  }
  return 0;
}

function mapAlert(alert: BackendAlert): Alert {
  const symbol = alert.related_assets[0] ?? "N/A";
  const title = preferredText(alert.title_zh, alert.title);
  const narrative = preferredText(alert.summary_zh, alert.summary);
  return {
    id: alert.id,
    symbol,
    symbolName: symbol,
    evaluator: alert.type,
    severity: toSeverity(alert.severity),
    confidence: alert.confidence,
    sampleSize: alert.trigger_chain.length,
    triggeredAt: alert.triggered_at,
    title,
    titleOriginal: alert.title_original ?? alert.title,
    titleZh: alert.title_zh,
    narrative,
    narrativeOriginal: alert.summary_original ?? alert.summary,
    narrativeZh: alert.summary_zh,
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

function recommendationSymbol(recommendation: BackendRecommendation): string | null {
  const leg = primaryRecommendationLeg(recommendation);
  const symbol = String(leg.asset || leg.symbol || "").trim();
  return symbol.length > 0 ? symbol : null;
}

function primaryRecommendationLeg(recommendation: BackendRecommendation): BackendLeg {
  return recommendation.legs.find((leg) => leg.direction === "long" || leg.direction === "short") ?? recommendation.legs[0] ?? {};
}

function recommendationDirection(recommendation: BackendRecommendation): Direction | null {
  const leg = primaryRecommendationLeg(recommendation);
  if (leg.direction === "long" || leg.direction === "short") {
    return leg.direction;
  }
  const action = recommendation.recommended_action.toLowerCase();
  if (action.includes("short") || action.includes("sell")) return "short";
  if (action.includes("long") || action.includes("buy")) return "long";
  return null;
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

function positiveNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = numeric(value);
    if (parsed > 0) return parsed;
  }
  return null;
}

function inferredStopLoss(entryPrice: number | null, direction: Direction): number {
  const entry = entryPrice ?? 1;
  return direction === "long" ? entry * 0.97 : entry * 1.03;
}

function inferredTakeProfit(
  entryPrice: number | null,
  direction: Direction,
  riskRewardRatio?: number | null
): number {
  const entry = entryPrice ?? 1;
  const reward = Math.max(1.5, riskRewardRatio ?? 1.8) * 0.03;
  return direction === "long" ? entry * (1 + reward) : entry * (1 - reward);
}

function riskPercentFromPlan(entryPrice: number | null, stopLoss: number, direction: Direction): number {
  const entry = entryPrice ?? 1;
  return direction === "long"
    ? ((stopLoss - entry) / entry) * 100
    : ((entry - stopLoss) / entry) * 100;
}

function rewardPercentFromPlan(entryPrice: number | null, takeProfit: number, direction: Direction): number {
  const entry = entryPrice ?? 1;
  return direction === "long"
    ? ((takeProfit - entry) / entry) * 100
    : ((entry - takeProfit) / entry) * 100;
}

function normalizedScore(score: number): number {
  return score > 1 ? clamp(score / 100, 0, 1) : clamp(score, 0, 1);
}

function normalizedMarginUsage(marginRequired: number): number {
  if (marginRequired <= 1) return marginRequired * 100;
  if (marginRequired <= 100) return marginRequired;
  return clamp((marginRequired / 1_000_000) * 100, 0, 50);
}

function normalizedPortfolioRisk(portfolioFitScore: number): number {
  return clamp((100 - portfolioFitScore) / 5, 1, 20);
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

function rootSymbols(values: string[]): string[] {
  return values
    .map((value) => value.replace(/\d+/g, "").replace(/[^A-Za-z]/g, "").toUpperCase())
    .filter((value) => value.length > 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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
