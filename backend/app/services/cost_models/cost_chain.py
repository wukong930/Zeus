from dataclasses import dataclass
from typing import Any

from app.services.cost_models.configs import FERROUS_FORMULAS
from app.services.cost_models.framework import CostFormula, CostModelResult

FERROUS_CHAIN_ORDER = ("JM", "J", "I", "RB", "HC")
FERROUS_UPSTREAM = {
    "JM": [],
    "J": ["JM"],
    "I": [],
    "RB": ["I", "J"],
    "HC": ["I", "J", "RB"],
}


@dataclass(frozen=True)
class CostChainResult:
    sector: str
    symbols: list[str]
    results: dict[str, CostModelResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "symbols": self.symbols,
            "results": {
                symbol: result.to_snapshot_payload()
                for symbol, result in self.results.items()
            },
        }


def get_cost_formula(symbol: str) -> CostFormula:
    normalized = symbol.upper()
    formula = FERROUS_FORMULAS.get(normalized)
    if formula is None:
        raise ValueError(f"Unsupported cost model symbol: {symbol}")
    return formula


def calculate_cost_chain(
    *,
    symbols: tuple[str, ...] = FERROUS_CHAIN_ORDER,
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
) -> CostChainResult:
    inputs_by_symbol = inputs_by_symbol or {}
    current_prices = current_prices or {}
    results: dict[str, CostModelResult] = {}

    for symbol in symbols:
        normalized = symbol.upper()
        formula = get_cost_formula(normalized)
        result = formula.calculate(
            inputs_by_symbol.get(normalized, {}),
            upstream=results,
            current_price=current_prices.get(normalized),
        )
        results[normalized] = result

    return CostChainResult(sector="ferrous", symbols=list(symbols), results=results)


def calculate_symbol_cost(
    symbol: str,
    *,
    inputs_by_symbol: dict[str, dict[str, Any]] | None = None,
    current_prices: dict[str, float | None] | None = None,
) -> CostModelResult:
    normalized = symbol.upper()
    if normalized in {"RB", "HC"}:
        return calculate_cost_chain(
            symbols=FERROUS_CHAIN_ORDER,
            inputs_by_symbol=inputs_by_symbol,
            current_prices=current_prices,
        ).results[normalized]
    if normalized == "J":
        return calculate_cost_chain(
            symbols=("JM", "J"),
            inputs_by_symbol=inputs_by_symbol,
            current_prices=current_prices,
        ).results[normalized]
    return get_cost_formula(normalized).calculate(
        (inputs_by_symbol or {}).get(normalized, {}),
        current_price=(current_prices or {}).get(normalized),
    )
