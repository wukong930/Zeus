from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MarketDataCreate(BaseModel):
    source_key: str | None = None
    market: str
    exchange: str
    commodity: str
    symbol: str
    contract_month: str
    contract_id: UUID | None = None
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    settle: float | None = None
    volume: float
    open_interest: float | None = None
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    vintage_at: datetime | None = None


class MarketDataRead(MarketDataCreate, ORMModel):
    id: UUID
    ingested_at: datetime


class IndustryDataCreate(BaseModel):
    source_key: str | None = None
    symbol: str
    data_type: str
    value: float
    unit: str
    source: str
    timestamp: datetime
    vintage_at: datetime | None = None


class IndustryDataRead(IndustryDataCreate, ORMModel):
    id: UUID
    ingested_at: datetime


class ContractCreate(BaseModel):
    symbol: str
    exchange: str | None = None
    commodity: str | None = None
    contract_month: str
    expiry_date: date | None = None
    is_main: bool = False
    main_from: datetime | None = None
    main_until: datetime | None = None
    volume: float | None = None
    open_interest: float | None = None


class ContractRead(ContractCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class AlertCreate(BaseModel):
    title: str
    summary: str
    severity: str
    category: str
    type: str
    status: str = "active"
    triggered_at: datetime
    expires_at: datetime | None = None
    confidence: float
    adversarial_passed: bool = False
    related_assets: list[str] = Field(default_factory=list)
    spread_info: dict[str, Any] | None = None
    trigger_chain: list[dict[str, Any]] = Field(default_factory=list)
    risk_items: list[str] = Field(default_factory=list)
    manual_check_items: list[str] = Field(default_factory=list)
    one_liner: str | None = None
    related_strategy_id: UUID | None = None
    related_recommendation_id: UUID | None = None
    related_research_id: UUID | None = None
    invalidation_reason: str | None = None


class AlertRead(AlertCreate, ORMModel):
    id: UUID
    updated_at: datetime


class NewsEventCreate(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    raw_url: str | None = None
    title: str = Field(min_length=1)
    summary: str | None = None
    content_text: str | None = None
    published_at: datetime
    event_type: str = Field(
        pattern="^(policy|supply|demand|inventory|geopolitical|weather|breaking)$"
    )
    affected_symbols: list[str] = Field(default_factory=list)
    direction: str = Field(pattern="^(bullish|bearish|mixed|unclear)$")
    severity: int = Field(ge=1, le=5)
    time_horizon: str = Field(pattern="^(immediate|short|medium|long)$")
    llm_confidence: float = Field(ge=0, le=1)
    source_count: int = Field(default=1, ge=1)
    verification_status: str | None = None
    dedup_hash: str | None = None
    extraction_payload: dict[str, Any] = Field(default_factory=dict)


class NewsEventRead(NewsEventCreate, ORMModel):
    id: UUID
    summary: str
    requires_manual_confirmation: bool
    created_at: datetime
    updated_at: datetime


class StrategyCreate(BaseModel):
    name: str
    description: str
    status: str = "draft"
    hypothesis: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    related_alert_ids: list[str] = Field(default_factory=list)
    recommendation_history: list[str] = Field(default_factory=list)
    execution_feedback_ids: list[str] = Field(default_factory=list)
    last_activated_at: datetime | None = None
    notes: str | None = None


class StrategyRead(StrategyCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class RecommendationCreate(BaseModel):
    strategy_id: UUID | None = None
    alert_id: UUID | None = None
    status: str = "pending"
    recommended_action: str
    legs: list[dict[str, Any]] = Field(default_factory=list)
    priority_score: float
    portfolio_fit_score: float
    margin_efficiency_score: float
    margin_required: float
    reasoning: str
    one_liner: str | None = None
    risk_items: list[str] = Field(default_factory=list)
    expires_at: datetime
    deferred_until: datetime | None = None
    ignored_reason: str | None = None
    execution_feedback_id: UUID | None = None
    max_holding_days: int | None = None
    position_size_pct: float | None = None
    risk_reward_ratio: float | None = None
    backtest_summary: dict[str, Any] | None = None


class RecommendationRead(RecommendationCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PositionCreate(BaseModel):
    strategy_id: UUID | None = None
    strategy_name: str | None = None
    recommendation_id: UUID | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list)
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


class PositionRead(PositionCreate, ORMModel):
    id: UUID
