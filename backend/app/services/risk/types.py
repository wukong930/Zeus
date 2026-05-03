from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

Direction = Literal["long", "short"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RiskLeg:
    asset: str
    direction: Direction
    size: float
    current_price: float
    entry_price: float | None = None
    unit: str | None = None
    unrealized_pnl: float | None = None
    margin_used: float | None = None


@dataclass(frozen=True, slots=True)
class RiskPosition:
    id: str
    legs: tuple[RiskLeg, ...]
    status: str = "open"
    strategy_name: str | None = None


@dataclass(frozen=True, slots=True)
class RiskMarketPoint:
    symbol: str
    timestamp: datetime
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    open_interest: float | None = None


@dataclass(frozen=True, slots=True)
class VaRResult:
    var95: float
    var99: float
    cvar95: float
    cvar99: float
    horizon: int
    method: str = "combined"
    calculated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StressScenario:
    name: str
    description: str
    shocks: dict[str, float]
    historical: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PositionImpact:
    position_id: str
    strategy_name: str
    pnl: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StressTestResult:
    scenario: str
    description: str
    portfolio_pnl: float
    position_impacts: tuple[PositionImpact, ...]

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "description": self.description,
            "portfolio_pnl": self.portfolio_pnl,
            "position_impacts": [impact.to_dict() for impact in self.position_impacts],
        }


@dataclass(frozen=True, slots=True)
class CorrelationMatrix:
    symbols: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    window: int
    calculated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "symbols": list(self.symbols),
            "matrix": [list(row) for row in self.matrix],
            "window": self.window,
            "calculated_at": self.calculated_at,
        }
