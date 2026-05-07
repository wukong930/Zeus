import json
import math
import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS = 40
MAX_GOVERNANCE_JSON_OBJECT_KEYS = 80
MAX_GOVERNANCE_JSON_LIST_ITEMS = 120
MAX_GOVERNANCE_JSON_DEPTH = 6
MAX_GOVERNANCE_JSON_NODES = 500
MAX_GOVERNANCE_JSON_BYTES = 32_768
MAX_GOVERNANCE_JSON_KEY_LENGTH = 80
MAX_GOVERNANCE_JSON_STRING_LENGTH = 1000
MAX_GOVERNANCE_TEXT_LENGTH = 4000
MAX_TRADE_LEGS = 8
MAX_TRADE_RISK_ITEMS = 20
MAX_POSITION_PROPAGATION_NODES = 40
MAX_TRADE_ITEM_TEXT_LENGTH = 800
MAX_STRATEGY_REFERENCES = 100
MAX_STRATEGY_REFERENCE_LENGTH = 80
MAX_INGEST_SOURCE_KEY_LENGTH = 160
MAX_INGEST_SYMBOL_LENGTH = 32
MAX_INGEST_TEXT_LENGTH = 120
MAX_INGEST_ABS_VALUE = 1_000_000_000_000.0
MAX_NEWS_TITLE_LENGTH = 300
MAX_NEWS_SUMMARY_LENGTH = 1200
MAX_NEWS_CONTENT_LENGTH = 20_000
MAX_NEWS_URL_LENGTH = 1000
MAX_NEWS_AFFECTED_SYMBOLS = 20
MAX_ALERT_TITLE_LENGTH = 300
MAX_ALERT_SUMMARY_LENGTH = 2000
MAX_ALERT_ONE_LINER_LENGTH = 600
MAX_ALERT_RELATED_ASSETS = 20
MAX_ALERT_TRIGGER_STEPS = 30
MAX_POSITION_LOTS = 1_000_000.0
MAX_POSITION_REASON_LENGTH = 80
MAX_POSITION_STRATEGY_NAME_LENGTH = 160


class MarketDataCreate(StrictInputModel):
    source_key: str | None = Field(default=None, max_length=MAX_INGEST_SOURCE_KEY_LENGTH)
    market: str = Field(min_length=1, max_length=10)
    exchange: str = Field(min_length=1, max_length=20)
    commodity: str = Field(min_length=1, max_length=MAX_INGEST_TEXT_LENGTH)
    symbol: str = Field(min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH)
    contract_month: str = Field(min_length=1, max_length=20)
    contract_id: UUID | None = None
    timestamp: datetime
    open: float = Field(gt=0, le=MAX_INGEST_ABS_VALUE)
    high: float = Field(gt=0, le=MAX_INGEST_ABS_VALUE)
    low: float = Field(gt=0, le=MAX_INGEST_ABS_VALUE)
    close: float = Field(gt=0, le=MAX_INGEST_ABS_VALUE)
    settle: float | None = Field(default=None, gt=0, le=MAX_INGEST_ABS_VALUE)
    volume: float = Field(ge=0, le=MAX_INGEST_ABS_VALUE)
    open_interest: float | None = Field(default=None, ge=0, le=MAX_INGEST_ABS_VALUE)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    vintage_at: datetime | None = None

    @model_validator(mode="after")
    def validate_ohlc(self) -> "MarketDataCreate":
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must be less than or equal to open, high, and close")
        return self


class MarketDataRead(MarketDataCreate, ORMModel):
    id: UUID
    ingested_at: datetime


class IndustryDataCreate(StrictInputModel):
    source_key: str | None = Field(default=None, max_length=MAX_INGEST_SOURCE_KEY_LENGTH)
    symbol: str = Field(min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH)
    data_type: str = Field(min_length=1, max_length=30)
    value: float = Field(ge=-MAX_INGEST_ABS_VALUE, le=MAX_INGEST_ABS_VALUE)
    unit: str = Field(min_length=1, max_length=20)
    source: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    vintage_at: datetime | None = None


class IndustryDataRead(IndustryDataCreate, ORMModel):
    id: UUID
    ingested_at: datetime


class ContractCreate(StrictInputModel):
    symbol: str = Field(min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH)
    exchange: str | None = Field(default=None, max_length=20)
    commodity: str | None = Field(default=None, max_length=MAX_INGEST_TEXT_LENGTH)
    contract_month: str = Field(min_length=1, max_length=20)
    expiry_date: date | None = None
    is_main: bool = False
    main_from: datetime | None = None
    main_until: datetime | None = None
    volume: float | None = Field(default=None, ge=0, le=MAX_INGEST_ABS_VALUE)
    open_interest: float | None = Field(default=None, ge=0, le=MAX_INGEST_ABS_VALUE)


class ContractRead(ContractCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class AlertCreate(StrictInputModel):
    title: str = Field(min_length=1, max_length=MAX_ALERT_TITLE_LENGTH)
    summary: str = Field(min_length=1, max_length=MAX_ALERT_SUMMARY_LENGTH)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    category: str = Field(min_length=1, max_length=20)
    type: str = Field(min_length=1, max_length=30)
    status: str = Field(default="active", max_length=20)
    triggered_at: datetime
    expires_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    adversarial_passed: bool = False
    llm_involved: bool = False
    confidence_tier: str = Field(default="notify", pattern="^(auto|notify|confirm)$")
    human_action_required: bool = False
    human_action_deadline: datetime | None = None
    dedup_suppressed: bool = False
    related_assets: list[str] = Field(default_factory=list, max_length=MAX_ALERT_RELATED_ASSETS)
    spread_info: dict[str, Any] | None = None
    trigger_chain: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_ALERT_TRIGGER_STEPS)
    risk_items: list[str] = Field(default_factory=list, max_length=MAX_TRADE_RISK_ITEMS)
    manual_check_items: list[str] = Field(default_factory=list, max_length=MAX_TRADE_RISK_ITEMS)
    one_liner: str | None = Field(default=None, max_length=MAX_ALERT_ONE_LINER_LENGTH)
    related_strategy_id: UUID | None = None
    related_recommendation_id: UUID | None = None
    related_research_id: UUID | None = None
    invalidation_reason: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("related_assets")
    @classmethod
    def normalize_related_assets(cls, value: list[str]) -> list[str]:
        symbols: list[str] = []
        for symbol in value:
            normalized = str(symbol).strip().upper()
            if not normalized:
                continue
            if len(normalized) > MAX_INGEST_SYMBOL_LENGTH:
                raise ValueError(
                    f"related asset entries can be at most {MAX_INGEST_SYMBOL_LENGTH} characters"
                )
            symbols.append(normalized)
        return list(dict.fromkeys(symbols))

    @field_validator("spread_info")
    @classmethod
    def validate_spread_info(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            validate_governance_json_object(value, field_name="spread_info")
        return value

    @field_validator("trigger_chain")
    @classmethod
    def validate_trigger_chain(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for step in value:
            validate_governance_json_object(step, field_name="trigger_chain")
        return value

    @field_validator("risk_items", "manual_check_items")
    @classmethod
    def validate_alert_item_text(cls, value: list[str]) -> list[str]:
        for item in value:
            if len(item) > MAX_TRADE_ITEM_TEXT_LENGTH:
                raise ValueError(
                    "alert item entries can be at most "
                    f"{MAX_TRADE_ITEM_TEXT_LENGTH} characters"
                )
        return value


class AlertRead(AlertCreate, ORMModel):
    id: UUID
    updated_at: datetime


class NewsEventCreate(StrictInputModel):
    source: str = Field(min_length=1, max_length=50)
    raw_url: str | None = Field(default=None, max_length=MAX_NEWS_URL_LENGTH)
    title: str = Field(min_length=1, max_length=MAX_NEWS_TITLE_LENGTH)
    summary: str | None = Field(default=None, max_length=MAX_NEWS_SUMMARY_LENGTH)
    content_text: str | None = Field(default=None, max_length=MAX_NEWS_CONTENT_LENGTH)
    published_at: datetime
    event_type: str = Field(
        pattern="^(policy|supply|demand|inventory|geopolitical|weather|breaking)$"
    )
    affected_symbols: list[str] = Field(default_factory=list, max_length=MAX_NEWS_AFFECTED_SYMBOLS)
    direction: str = Field(pattern="^(bullish|bearish|mixed|unclear)$")
    severity: int = Field(ge=1, le=5)
    time_horizon: str = Field(pattern="^(immediate|short|medium|long)$")
    llm_confidence: float = Field(ge=0, le=1)
    source_count: int = Field(default=1, ge=1, le=50)
    verification_status: str | None = Field(default=None, max_length=30)
    dedup_hash: str | None = Field(default=None, max_length=64)
    extraction_payload: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )

    @field_validator("affected_symbols")
    @classmethod
    def normalize_affected_symbols(cls, value: list[str]) -> list[str]:
        symbols: list[str] = []
        for symbol in value:
            normalized = str(symbol).strip().upper()
            if not normalized:
                continue
            if len(normalized) > MAX_INGEST_SYMBOL_LENGTH:
                raise ValueError(
                    f"affected symbol entries can be at most {MAX_INGEST_SYMBOL_LENGTH} characters"
                )
            symbols.append(normalized)
        return sorted(dict.fromkeys(symbols))

    @field_validator("extraction_payload")
    @classmethod
    def validate_extraction_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="extraction_payload")


class NewsEventRead(NewsEventCreate, ORMModel):
    id: UUID
    summary: str
    requires_manual_confirmation: bool
    created_at: datetime
    updated_at: datetime


class HumanDecisionCreate(StrictInputModel):
    alert_id: UUID | None = None
    signal_track_id: UUID | None = None
    decision: str = Field(pattern="^(approve|reject|modify)$")
    confidence_override: float | None = Field(default=None, ge=0, le=1)
    reasoning: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)
    decided_by: str | None = Field(default=None, max_length=80)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="payload")


class HumanDecisionRead(HumanDecisionCreate, ORMModel):
    id: UUID
    created_at: datetime


class UserFeedbackCreate(StrictInputModel):
    alert_id: UUID | None = None
    recommendation_id: UUID | None = None
    agree: str = Field(pattern="^(agree|disagree|uncertain)$")
    disagreement_reason: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)
    will_trade: str = Field(pattern="^(will_trade|will_not_trade|partial)$")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="metadata")


class UserFeedbackRead(ORMModel):
    id: UUID
    alert_id: UUID | None = None
    recommendation_id: UUID | None = None
    signal_type: str | None = None
    category: str | None = None
    agree: str
    disagreement_reason: str | None = None
    will_trade: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    recorded_at: datetime


def validate_governance_json_object(value: dict[str, Any], *, field_name: str) -> dict[str, Any]:
    _validate_governance_json_shape(value, field_name=field_name)
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_GOVERNANCE_JSON_BYTES:
        raise ValueError(f"{field_name} must be at most {MAX_GOVERNANCE_JSON_BYTES} bytes")
    return value


def _validate_governance_json_shape(
    value: Any,
    *,
    field_name: str,
    depth: int = 0,
    nodes: int = 0,
) -> int:
    if depth > MAX_GOVERNANCE_JSON_DEPTH:
        raise ValueError(f"{field_name} nesting cannot exceed {MAX_GOVERNANCE_JSON_DEPTH} levels")
    nodes += 1
    if nodes > MAX_GOVERNANCE_JSON_NODES:
        raise ValueError(f"{field_name} can include at most {MAX_GOVERNANCE_JSON_NODES} nodes")
    if isinstance(value, dict):
        if len(value) > MAX_GOVERNANCE_JSON_OBJECT_KEYS:
            raise ValueError(
                f"{field_name} objects can include at most {MAX_GOVERNANCE_JSON_OBJECT_KEYS} keys"
            )
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty strings")
            if len(key) > MAX_GOVERNANCE_JSON_KEY_LENGTH:
                raise ValueError(
                    f"{field_name} keys can be at most {MAX_GOVERNANCE_JSON_KEY_LENGTH} characters"
                )
            nodes = _validate_governance_json_shape(
                item,
                field_name=field_name,
                depth=depth + 1,
                nodes=nodes,
            )
        return nodes
    if isinstance(value, list):
        if len(value) > MAX_GOVERNANCE_JSON_LIST_ITEMS:
            raise ValueError(
                f"{field_name} lists can include at most {MAX_GOVERNANCE_JSON_LIST_ITEMS} items"
            )
        for item in value:
            nodes = _validate_governance_json_shape(
                item,
                field_name=field_name,
                depth=depth + 1,
                nodes=nodes,
            )
        return nodes
    if isinstance(value, str):
        if len(value) > MAX_GOVERNANCE_JSON_STRING_LENGTH:
            raise ValueError(
                f"{field_name} strings can be at most {MAX_GOVERNANCE_JSON_STRING_LENGTH} characters"
            )
        return nodes
    if value is None or isinstance(value, (bool, int)):
        return nodes
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} numeric values must be finite")
        return nodes
    raise ValueError(f"{field_name} values must be JSON primitives, objects, or lists")


class LLMUsageSummaryRead(BaseModel):
    module: str
    period_start: date
    period_end: date
    calls: int
    cache_hits: int
    estimated_cost_usd: float
    input_tokens: int
    output_tokens: int


class CostSnapshotRead(ORMModel):
    id: UUID
    symbol: str
    name: str
    sector: str
    snapshot_date: date
    current_price: float | None = None
    total_unit_cost: float
    breakeven_p25: float
    breakeven_p50: float
    breakeven_p75: float
    breakeven_p90: float
    profit_margin: float | None = None
    cost_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_pct: float
    formula_version: str
    created_at: datetime


class CostModelRead(BaseModel):
    symbol: str
    name: str
    sector: str
    current_price: float | None = None
    total_unit_cost: float
    breakevens: dict[str, float]
    profit_margin: float | None = None
    cost_breakdown: list[dict[str, Any]]
    inputs: dict[str, Any]
    data_sources: list[dict[str, Any]]
    uncertainty_pct: float
    formula_version: str


MAX_COST_SIMULATION_SYMBOLS = 20
MAX_COST_SIMULATION_INPUTS_PER_SYMBOL = 40
MAX_COST_SIMULATION_SYMBOL_LENGTH = 20
MAX_COST_SIMULATION_INPUT_KEY_LENGTH = 80
MAX_COST_SIMULATION_ABS_VALUE = 1_000_000.0


class CostSimulationRequest(StrictInputModel):
    inputs_by_symbol: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        max_length=MAX_COST_SIMULATION_SYMBOLS,
    )
    current_prices: dict[str, float | None] = Field(
        default_factory=dict,
        max_length=MAX_COST_SIMULATION_SYMBOLS,
    )

    @field_validator("inputs_by_symbol")
    @classmethod
    def normalize_inputs_by_symbol(
        cls,
        value: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        normalized: dict[str, dict[str, float]] = {}
        for symbol, raw_inputs in value.items():
            normalized_symbol = normalize_commodity_symbol(symbol)
            if len(raw_inputs) > MAX_COST_SIMULATION_INPUTS_PER_SYMBOL:
                raise ValueError(
                    "cost simulation inputs support at most "
                    f"{MAX_COST_SIMULATION_INPUTS_PER_SYMBOL} values per symbol"
                )
            inputs = normalized.setdefault(normalized_symbol, {})
            for key, raw_value in raw_inputs.items():
                normalized_key = str(key).strip()
                if not normalized_key:
                    raise ValueError("cost simulation input keys must be non-empty strings")
                if len(normalized_key) > MAX_COST_SIMULATION_INPUT_KEY_LENGTH:
                    raise ValueError(
                        "cost simulation input keys can be at most "
                        f"{MAX_COST_SIMULATION_INPUT_KEY_LENGTH} characters"
                    )
                inputs[normalized_key] = bounded_cost_simulation_float(raw_value)
        return normalized

    @field_validator("current_prices")
    @classmethod
    def normalize_current_prices(
        cls,
        value: dict[str, float | None],
    ) -> dict[str, float | None]:
        normalized: dict[str, float | None] = {}
        for symbol, raw_value in value.items():
            normalized_symbol = normalize_commodity_symbol(symbol)
            if raw_value is None:
                normalized[normalized_symbol] = None
                continue
            price = bounded_cost_simulation_float(raw_value)
            if price <= 0:
                raise ValueError("cost simulation current prices must be greater than zero")
            normalized[normalized_symbol] = price
        return normalized


def normalize_commodity_symbol(value: Any) -> str:
    normalized = re.sub(r"\d+", "", str(value).strip()).upper()
    if not normalized:
        raise ValueError("commodity symbol must be non-empty")
    if len(normalized) > MAX_COST_SIMULATION_SYMBOL_LENGTH:
        raise ValueError(
            f"commodity symbols can be at most {MAX_COST_SIMULATION_SYMBOL_LENGTH} characters"
        )
    return normalized


def bounded_cost_simulation_float(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("cost simulation numeric values must be finite")
    if abs(parsed) > MAX_COST_SIMULATION_ABS_VALUE:
        raise ValueError(
            "cost simulation numeric values must be between "
            f"{-MAX_COST_SIMULATION_ABS_VALUE:g} and {MAX_COST_SIMULATION_ABS_VALUE:g}"
        )
    return parsed


class CostChainRead(BaseModel):
    sector: str
    symbols: list[str]
    results: dict[str, CostModelRead]


class CostBenchmarkComparisonRead(BaseModel):
    symbol: str
    metric: str
    model_value: float
    public_value: float
    error_pct: float
    within_tolerance: bool
    source: str
    observed_at: datetime
    note: str


class CostSignalCaseRead(BaseModel):
    case_id: str
    title: str
    expected_signals: list[str]
    triggered_signals: list[str]
    passed: bool
    note: str


class CostQualityReportRead(BaseModel):
    sector: str
    generated_at: datetime
    benchmark_error_avg_pct: float
    benchmark_error_max_pct: float
    benchmark_pass_rate: float
    signal_case_hit_rate: float
    data_quality_score: int
    paid_data_recommendation: str
    preferred_vendor: str | None = None
    benchmark_comparisons: list[CostBenchmarkComparisonRead]
    signal_cases: list[CostSignalCaseRead]
    limitations: list[str]


class StrategyCreate(StrictInputModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=MAX_GOVERNANCE_TEXT_LENGTH)
    status: str = Field(default="draft", max_length=30)
    hypothesis: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )
    validation: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )
    related_alert_ids: list[str] = Field(default_factory=list, max_length=MAX_STRATEGY_REFERENCES)
    recommendation_history: list[str] = Field(default_factory=list, max_length=MAX_STRATEGY_REFERENCES)
    execution_feedback_ids: list[str] = Field(default_factory=list, max_length=MAX_STRATEGY_REFERENCES)
    last_activated_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("hypothesis")
    @classmethod
    def validate_hypothesis(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="hypothesis")

    @field_validator("validation")
    @classmethod
    def validate_validation(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="validation")

    @field_validator("related_alert_ids", "recommendation_history", "execution_feedback_ids")
    @classmethod
    def validate_reference_list(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("strategy reference entries must be non-empty strings")
            if len(item) > MAX_STRATEGY_REFERENCE_LENGTH:
                raise ValueError(
                    "strategy reference entries can be at most "
                    f"{MAX_STRATEGY_REFERENCE_LENGTH} characters"
                )
        return value


class StrategyRead(StrategyCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class RecommendationCreate(StrictInputModel):
    strategy_id: UUID | None = None
    alert_id: UUID | None = None
    status: str = "pending"
    recommended_action: str
    legs: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_TRADE_LEGS)
    priority_score: float
    portfolio_fit_score: float
    margin_efficiency_score: float
    margin_required: float
    reasoning: str
    one_liner: str | None = None
    risk_items: list[str] = Field(default_factory=list, max_length=MAX_TRADE_RISK_ITEMS)
    expires_at: datetime
    deferred_until: datetime | None = None
    ignored_reason: str | None = None
    execution_feedback_id: UUID | None = None
    max_holding_days: int | None = None
    position_size_pct: float | None = None
    risk_reward_ratio: float | None = None
    backtest_summary: dict[str, Any] | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    actual_entry: float | None = None
    actual_exit: float | None = None
    actual_exit_reason: str | None = None
    pnl_realized: float | None = None
    mae: float | None = None
    mfe: float | None = None
    holding_period_days: float | None = None

    @field_validator("legs")
    @classmethod
    def validate_legs(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for leg in value:
            validate_governance_json_object(leg, field_name="legs")
        return value

    @field_validator("risk_items")
    @classmethod
    def validate_risk_items(cls, value: list[str]) -> list[str]:
        for item in value:
            if len(item) > MAX_TRADE_ITEM_TEXT_LENGTH:
                raise ValueError(
                    f"risk_items entries can be at most {MAX_TRADE_ITEM_TEXT_LENGTH} characters"
                )
        return value

    @field_validator("backtest_summary")
    @classmethod
    def validate_backtest_summary(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            validate_governance_json_object(value, field_name="backtest_summary")
        return value


class RecommendationRead(RecommendationCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PositionCreate(StrictInputModel):
    strategy_id: UUID | None = None
    strategy_name: str | None = None
    recommendation_id: UUID | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_TRADE_LEGS)
    opened_at: datetime
    entry_spread: float
    current_spread: float
    spread_unit: str
    unrealized_pnl: float
    total_margin_used: float
    exit_condition: str
    target_z_score: float
    current_z_score: float
    half_life_days: float
    days_held: float
    status: str = "open"
    closed_at: datetime | None = None
    realized_pnl: float | None = None
    manual_entry: bool = False
    avg_entry_price: float | None = None
    monitoring_priority: int = 50
    propagation_nodes: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=MAX_POSITION_PROPAGATION_NODES,
    )
    last_updated_at: datetime | None = None
    stale_since: datetime | None = None
    data_mode: str = "position_aware"

    @field_validator("legs")
    @classmethod
    def validate_position_legs(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for leg in value:
            validate_governance_json_object(leg, field_name="legs")
        return value

    @field_validator("propagation_nodes")
    @classmethod
    def validate_propagation_nodes(
        cls,
        value: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for node in value:
            validate_governance_json_object(node, field_name="propagation_nodes")
        return value


class PositionRead(PositionCreate, ORMModel):
    id: UUID


class PositionMinimalCreate(StrictInputModel):
    symbol: str = Field(min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH)
    direction: str = Field(pattern="^(long|short)$")
    lots: float = Field(gt=0, le=MAX_POSITION_LOTS)
    avg_entry_price: float = Field(gt=0, le=MAX_INGEST_ABS_VALUE)
    opened_at: datetime
    category: str = Field(default="unknown", min_length=1, max_length=30)
    recommendation_id: UUID | None = None
    strategy_name: str | None = Field(default=None, max_length=MAX_POSITION_STRATEGY_NAME_LENGTH)
    total_margin_used: float = Field(default=0, ge=0, le=MAX_INGEST_ABS_VALUE)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class PositionCloseRequest(StrictInputModel):
    actual_exit: float | None = Field(
        default=None,
        ge=-MAX_INGEST_ABS_VALUE,
        le=MAX_INGEST_ABS_VALUE,
    )
    actual_exit_reason: str = Field(default="manual_close", max_length=MAX_POSITION_REASON_LENGTH)
    realized_pnl: float | None = Field(
        default=None,
        ge=-MAX_INGEST_ABS_VALUE,
        le=MAX_INGEST_ABS_VALUE,
    )
    closed_at: datetime | None = None


class PositionResizeRequest(StrictInputModel):
    lots: float | None = Field(default=None, gt=0, le=MAX_POSITION_LOTS)
    fraction: float | None = Field(default=None, gt=0, le=1)
    reason: str | None = Field(default=None, max_length=MAX_POSITION_REASON_LENGTH)


class RecommendationAdoptRequest(StrictInputModel):
    opened_at: datetime | None = None
    actual_entry: float | None = Field(default=None, gt=0, le=MAX_INGEST_ABS_VALUE)
    lots: float = Field(default=1, gt=0, le=MAX_POSITION_LOTS)
    total_margin_used: float | None = Field(default=None, ge=0, le=MAX_INGEST_ABS_VALUE)
