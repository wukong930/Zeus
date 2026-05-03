from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


Severity = str


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_interest: float | None = None


@dataclass(frozen=True)
class IndustryPoint:
    value: float
    timestamp: datetime


@dataclass(frozen=True)
class SpreadStatistics:
    adf_p_value: float
    half_life: float
    spread_mean: float
    spread_std_dev: float
    current_z_score: float
    raw_spread_mean: float | None = None
    raw_spread_std_dev: float | None = None


@dataclass(frozen=True)
class TriggerStep:
    step: int
    label: str
    description: str
    confidence: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SpreadInfo:
    leg1: str
    leg2: str
    current_spread: float
    historical_mean: float
    sigma1_upper: float
    sigma1_lower: float
    z_score: float
    half_life: float
    adf_p_value: float
    unit: str = "price"


@dataclass(frozen=True)
class TriggerContext:
    symbol1: str
    category: str
    timestamp: datetime
    market_data: list[MarketBar] = field(default_factory=list)
    inventory: list[IndustryPoint] = field(default_factory=list)
    symbol2: str | None = None
    spread_stats: SpreadStatistics | None = None
    in_roll_window: bool = False


@dataclass(frozen=True)
class TriggerResult:
    signal_type: str
    triggered: bool
    severity: Severity
    confidence: float
    trigger_chain: list[TriggerStep]
    related_assets: list[str]
    risk_items: list[str]
    manual_check_items: list[str]
    title: str
    summary: str
    spread_info: SpreadInfo | None = None


class TriggerEvaluator(Protocol):
    signal_type: str

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        ...
