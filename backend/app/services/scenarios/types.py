from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    target_symbol: str
    shocks: dict[str, float]
    base_price: float | None = None
    days: int = 20
    simulations: int = 1000
    volatility_pct: float | None = None
    drift_pct: float = 0.0
    seed: int = 7
    max_depth: int = 3


@dataclass(frozen=True, slots=True)
class PropagationEdge:
    source: str
    target: str
    elasticity: float
    relationship: str
    lag_days: int = 1


@dataclass(frozen=True, slots=True)
class PropagationPath:
    root_symbol: str
    source_symbol: str
    target_symbol: str
    relationship: str
    elasticity: float
    input_shock: float
    impact: float
    depth: int
    lag_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_symbol": self.root_symbol,
            "source_symbol": self.source_symbol,
            "target_symbol": self.target_symbol,
            "relationship": self.relationship,
            "elasticity": round(self.elasticity, 4),
            "input_shock": round(self.input_shock, 6),
            "impact": round(self.impact, 6),
            "depth": self.depth,
            "lag_days": self.lag_days,
        }


@dataclass(frozen=True, slots=True)
class ImpactSummary:
    symbol: str
    direct_shock: float
    propagated_shock: float
    total_shock: float
    dominant_driver: str | None
    paths: tuple[PropagationPath, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direct_shock": round(self.direct_shock, 6),
            "propagated_shock": round(self.propagated_shock, 6),
            "total_shock": round(self.total_shock, 6),
            "dominant_driver": self.dominant_driver,
            "paths": [path.to_dict() for path in self.paths],
        }


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    shocks: dict[str, float]
    impacts: tuple[ImpactSummary, ...]
    key_paths: tuple[PropagationPath, ...]
    max_depth: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "shocks": {symbol: round(shock, 6) for symbol, shock in self.shocks.items()},
            "impacts": [impact.to_dict() for impact in self.impacts],
            "key_paths": [path.to_dict() for path in self.key_paths],
            "max_depth": self.max_depth,
        }


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    target_symbol: str
    base_price: float
    days: int
    simulations: int
    volatility_pct: float
    drift_pct: float
    applied_shock: float
    terminal_distribution: dict[str, float]
    expected_terminal_price: float
    expected_return: float
    downside_probability: float
    sample_paths: tuple[tuple[float, ...], ...]
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_symbol": self.target_symbol,
            "base_price": round(self.base_price, 4),
            "days": self.days,
            "simulations": self.simulations,
            "volatility_pct": round(self.volatility_pct, 6),
            "drift_pct": round(self.drift_pct, 6),
            "applied_shock": round(self.applied_shock, 6),
            "terminal_distribution": {
                key: round(value, 4) for key, value in self.terminal_distribution.items()
            },
            "expected_terminal_price": round(self.expected_terminal_price, 4),
            "expected_return": round(self.expected_return, 6),
            "downside_probability": round(self.downside_probability, 6),
            "sample_paths": [list(path) for path in self.sample_paths],
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class ScenarioReport:
    target_symbol: str
    base_price: float
    request: ScenarioRequest
    what_if: WhatIfResult
    monte_carlo: MonteCarloResult
    narrative: str
    risk_points: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    narrative_source: str = "deterministic"
    scenario_id: str = field(default_factory=lambda: str(uuid4()))
    generated_at: str = field(default_factory=utc_now_iso)
    status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self.request)
        return {
            "scenario_id": self.scenario_id,
            "generated_at": self.generated_at,
            "status": self.status,
            "target_symbol": self.target_symbol,
            "base_price": round(self.base_price, 4),
            "request": payload,
            "what_if": self.what_if.to_dict(),
            "monte_carlo": self.monte_carlo.to_dict(),
            "narrative": self.narrative,
            "narrative_source": self.narrative_source,
            "risk_points": list(self.risk_points),
            "suggested_actions": list(self.suggested_actions),
        }
