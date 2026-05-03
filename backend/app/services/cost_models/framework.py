from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CostComponent:
    name: str
    value: float
    unit: str = "CNY/t"
    source: str = "public_fallback"
    uncertainty_pct: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "source": self.source,
            "uncertainty_pct": self.uncertainty_pct,
        }


@dataclass(frozen=True)
class CostInput:
    name: str
    value: float
    unit: str = "CNY/t"
    source: str = "public_fallback"
    updated_at: datetime | None = None
    uncertainty_pct: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "unit": self.unit,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "uncertainty_pct": self.uncertainty_pct,
        }


@dataclass(frozen=True)
class CostModelResult:
    symbol: str
    name: str
    sector: str
    unit_cost: float
    breakevens: dict[str, float]
    components: list[CostComponent]
    inputs: dict[str, CostInput]
    formula_version: str
    current_price: float | None = None
    uncertainty_pct: float = 0.05
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def profit_margin(self) -> float | None:
        if self.current_price is None or self.current_price <= 0:
            return None
        return round((self.current_price - self.unit_cost) / self.current_price, 6)

    @property
    def data_sources(self) -> list[dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for item in self.inputs.values():
            sources[item.source] = {
                "name": item.source,
                "unit": item.unit,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "uncertainty_pct": item.uncertainty_pct,
            }
        return list(sources.values())

    def to_snapshot_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "current_price": self.current_price,
            "total_unit_cost": round(self.unit_cost, 4),
            "breakeven_p25": self.breakevens["p25"],
            "breakeven_p50": self.breakevens["p50"],
            "breakeven_p75": self.breakevens["p75"],
            "breakeven_p90": self.breakevens["p90"],
            "profit_margin": self.profit_margin,
            "cost_breakdown": [component.to_dict() for component in self.components],
            "inputs": {key: item.to_dict() for key, item in self.inputs.items()},
            "data_sources": self.data_sources,
            "uncertainty_pct": self.uncertainty_pct,
            "formula_version": self.formula_version,
        }


class CostFormula:
    symbol: str
    name: str
    sector: str = "ferrous"
    version: str = "phase7a.v1"
    uncertainty_pct: float = 0.05
    capacity_cost_offsets: tuple[tuple[float, float], ...] = (
        (-0.10, 0.25),
        (-0.04, 0.25),
        (0.04, 0.25),
        (0.12, 0.25),
    )

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        raise NotImplementedError

    def result(
        self,
        *,
        unit_cost: float,
        components: list[CostComponent],
        inputs: dict[str, CostInput],
        current_price: float | None = None,
    ) -> CostModelResult:
        return CostModelResult(
            symbol=self.symbol,
            name=self.name,
            sector=self.sector,
            unit_cost=round(unit_cost, 4),
            breakevens=cost_curve_percentiles(
                unit_cost,
                self.capacity_cost_offsets,
            ),
            components=components,
            inputs=inputs,
            current_price=current_price,
            formula_version=self.version,
            uncertainty_pct=self.uncertainty_pct,
        )


def numeric_input(
    payload: dict[str, Any] | None,
    key: str,
    default: float,
    *,
    unit: str = "CNY/t",
    source: str = "public_fallback",
) -> CostInput:
    value = default
    if payload is not None and payload.get(key) is not None:
        value = float(payload[key])
    return CostInput(name=key, value=float(value), unit=unit, source=source)


def component(name: str, value: float, *, source: str = "formula") -> CostComponent:
    return CostComponent(name=name, value=float(value), source=source)


def cost_curve_percentiles(
    unit_cost: float,
    offsets_and_weights: tuple[tuple[float, float], ...],
) -> dict[str, float]:
    points = sorted(
        ((unit_cost * (1 + offset), weight) for offset, weight in offsets_and_weights),
        key=lambda item: item[0],
    )
    return {
        "p25": round(weighted_percentile(points, 0.25), 4),
        "p50": round(weighted_percentile(points, 0.50), 4),
        "p75": round(weighted_percentile(points, 0.75), 4),
        "p90": round(weighted_percentile(points, 0.90), 4),
    }


def weighted_percentile(points: list[tuple[float, float]], percentile: float) -> float:
    if not points:
        return 0.0
    total_weight = sum(max(weight, 0.0) for _, weight in points)
    if total_weight <= 0:
        return points[-1][0]
    target = total_weight * percentile
    cumulative = 0.0
    for value, weight in points:
        cumulative += max(weight, 0.0)
        if cumulative >= target:
            return value
    return points[-1][0]
