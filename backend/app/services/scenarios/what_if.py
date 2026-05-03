from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.services.risk.stress import symbol_prefix
from app.services.scenarios.types import (
    ImpactSummary,
    PropagationEdge,
    PropagationPath,
    WhatIfResult,
)

MAX_ABS_SHOCK = 0.8
MIN_PROPAGATED_IMPACT = 0.0005

PROPAGATION_EDGES: tuple[PropagationEdge, ...] = (
    PropagationEdge("NR", "RU", 0.72, "natural-rubber raw material pass-through", 2),
    PropagationEdge("NR", "BR", 0.30, "substitution spread", 3),
    PropagationEdge("RU", "NR", 0.38, "domestic futures feedback", 1),
    PropagationEdge("RU", "BR", 0.34, "synthetic substitution spread", 2),
    PropagationEdge("BR", "RU", 0.28, "substitute cost pressure", 2),
    PropagationEdge("BR", "NR", 0.22, "substitute demand pressure", 3),
    PropagationEdge("I", "RB", 0.58, "blast-furnace cost pass-through", 2),
    PropagationEdge("I", "HC", 0.50, "hot-coil cost pass-through", 2),
    PropagationEdge("J", "RB", 0.36, "coke cost pass-through", 2),
    PropagationEdge("J", "HC", 0.33, "hot-coil coke cost pass-through", 2),
    PropagationEdge("JM", "J", 0.65, "coking-coal to coke input cost", 2),
    PropagationEdge("JM", "RB", 0.22, "coking-coal indirect steel cost", 3),
    PropagationEdge("RB", "HC", 0.42, "steel product relative value", 1),
    PropagationEdge("HC", "RB", 0.38, "steel product relative value", 1),
    PropagationEdge("SC", "FU", 0.62, "refined fuel feedstock", 1),
    PropagationEdge("SC", "TA", 0.44, "aromatics chain feedstock", 3),
    PropagationEdge("SC", "EG", 0.28, "ethylene glycol energy cost", 3),
    PropagationEdge("FU", "SC", 0.32, "fuel-oil crude anchor", 1),
    PropagationEdge("TA", "EG", 0.24, "polyester complex spread", 2),
    PropagationEdge("CU", "ZN", 0.30, "base-metal macro beta", 1),
    PropagationEdge("CU", "AL", 0.28, "base-metal macro beta", 1),
    PropagationEdge("AL", "CU", 0.22, "base-metal macro beta", 1),
    PropagationEdge("ZN", "CU", 0.20, "base-metal macro beta", 1),
)


@dataclass(slots=True)
class _ImpactAccumulator:
    direct: float = 0.0
    propagated: float = 0.0
    driver_contributions: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    paths: list[PropagationPath] = field(default_factory=list)


def run_what_if(
    shocks: dict[str, float],
    *,
    max_depth: int = 3,
    edges: tuple[PropagationEdge, ...] = PROPAGATION_EDGES,
) -> WhatIfResult:
    normalized = normalize_shocks(shocks)
    edge_map = _edges_by_source(edges)
    accumulators: dict[str, _ImpactAccumulator] = defaultdict(_ImpactAccumulator)

    queue: deque[tuple[str, str, float, int, tuple[str, ...], int]] = deque()
    for symbol, shock in normalized.items():
        accumulators[symbol].direct += shock
        accumulators[symbol].driver_contributions[symbol] += shock
        queue.append((symbol, symbol, shock, 0, (symbol,), 0))

    while queue:
        root_symbol, source_symbol, input_shock, depth, visited, lag_days = queue.popleft()
        next_depth = depth + 1
        if next_depth > max_depth:
            continue

        for edge in edge_map.get(source_symbol, ()):
            if edge.target in visited:
                continue

            impact = input_shock * edge.elasticity
            if abs(impact) < MIN_PROPAGATED_IMPACT:
                continue

            total_lag_days = lag_days + edge.lag_days
            path = PropagationPath(
                root_symbol=root_symbol,
                source_symbol=edge.source,
                target_symbol=edge.target,
                relationship=edge.relationship,
                elasticity=edge.elasticity,
                input_shock=input_shock,
                impact=impact,
                depth=next_depth,
                lag_days=total_lag_days,
            )
            accumulator = accumulators[edge.target]
            accumulator.propagated += impact
            accumulator.driver_contributions[root_symbol] += impact
            accumulator.paths.append(path)
            queue.append(
                (
                    root_symbol,
                    edge.target,
                    impact,
                    next_depth,
                    (*visited, edge.target),
                    total_lag_days,
                )
            )

    impacts = tuple(
        ImpactSummary(
            symbol=symbol,
            direct_shock=_cap_shock(accumulator.direct),
            propagated_shock=_cap_shock(accumulator.propagated),
            total_shock=_cap_shock(accumulator.direct + accumulator.propagated),
            dominant_driver=_dominant_driver(accumulator.driver_contributions),
            paths=tuple(sorted(accumulator.paths, key=lambda item: abs(item.impact), reverse=True)),
        )
        for symbol, accumulator in sorted(accumulators.items())
    )
    key_paths = tuple(
        sorted(
            (path for impact in impacts for path in impact.paths),
            key=lambda item: abs(item.impact),
            reverse=True,
        )[:8]
    )
    return WhatIfResult(shocks=normalized, impacts=impacts, key_paths=key_paths, max_depth=max_depth)


def impact_for_symbol(result: WhatIfResult, symbol: str) -> ImpactSummary | None:
    normalized = symbol_prefix(symbol)
    return next((impact for impact in result.impacts if impact.symbol == normalized), None)


def normalize_shocks(shocks: dict[str, float]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for symbol, shock in shocks.items():
        root = symbol_prefix(str(symbol))
        if not root:
            continue
        normalized[root] = _cap_shock(normalized.get(root, 0.0) + float(shock))
    return dict(sorted(normalized.items()))


def _edges_by_source(edges: tuple[PropagationEdge, ...]) -> dict[str, tuple[PropagationEdge, ...]]:
    grouped: dict[str, list[PropagationEdge]] = defaultdict(list)
    for edge in edges:
        grouped[edge.source].append(edge)
    return {source: tuple(items) for source, items in grouped.items()}


def _dominant_driver(contributions: dict[str, float]) -> str | None:
    if not contributions:
        return None
    return max(contributions.items(), key=lambda item: abs(item[1]))[0]


def _cap_shock(value: float) -> float:
    return max(-MAX_ABS_SHOCK, min(MAX_ABS_SHOCK, value))
