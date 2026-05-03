from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import CommodityNode, RelationshipEdge
from app.services.adversarial.types import AdversarialCheckResult


@dataclass(frozen=True)
class StructuralEdge:
    source_symbol: str
    target_symbol: str
    type: str
    strength: float
    label: str | None = None
    propagation_direction: int | None = None


def evaluate_structural_counter(
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    edges: list[StructuralEdge] | None = None,
) -> AdversarialCheckResult:
    counterarguments = structural_counterarguments(
        signal=signal,
        context=context,
        edges=edges or [],
    )
    return AdversarialCheckResult(
        check_name="structural_counter",
        passed=len(counterarguments) == 0,
        score=float(len(counterarguments)),
        sample_size=len(counterarguments),
        reason=(
            "No structural counterarguments found."
            if not counterarguments
            else f"Found {len(counterarguments)} structural counterarguments."
        ),
        details={"counterarguments": counterarguments},
    )


def structural_counterarguments(
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    edges: list[StructuralEdge],
) -> list[dict[str, Any]]:
    arguments: list[dict[str, Any]] = []
    related_assets = {str(asset) for asset in signal.get("related_assets", [])}

    for edge in edges:
        if edge.source_symbol not in related_assets and edge.target_symbol not in related_assets:
            continue
        if (edge.propagation_direction or 0) < 0 or edge.type in {"substitute", "inverse"}:
            arguments.append(
                {
                    "type": "reverse_path",
                    "source": edge.source_symbol,
                    "target": edge.target_symbol,
                    "label": edge.label,
                    "strength": edge.strength,
                }
            )

    seasonal_factor = context.get("seasonal_factor")
    if isinstance(seasonal_factor, (int, float)) and seasonal_factor < 0:
        arguments.append(
            {
                "type": "seasonal_reversal",
                "seasonal_factor": seasonal_factor,
                "label": "Seasonality points against the signal direction.",
            }
        )

    substitute_pressure = context.get("substitute_pressure")
    if isinstance(substitute_pressure, (int, float)) and substitute_pressure > 0:
        arguments.append(
            {
                "type": "substitute_pressure",
                "substitute_pressure": substitute_pressure,
                "label": "Substitute pressure weakens the signal thesis.",
            }
        )

    opposing_factors = context.get("opposing_factors")
    if isinstance(opposing_factors, list) and opposing_factors:
        arguments.append(
            {
                "type": "opposing_factor",
                "items": opposing_factors,
                "label": "Context carries opposing factors.",
            }
        )

    return arguments


async def load_structural_edges(
    session: AsyncSession,
    *,
    symbols: list[str],
) -> list[StructuralEdge]:
    if not symbols:
        return []

    nodes = (
        await session.scalars(select(CommodityNode).where(CommodityNode.symbol.in_(symbols)))
    ).all()
    node_symbols = {node.id: node.symbol for node in nodes}
    if not node_symbols:
        return []
    node_ids = list(node_symbols)

    edges = (
        await session.scalars(
            select(RelationshipEdge).where(
                or_(
                    RelationshipEdge.source.in_(node_ids),
                    RelationshipEdge.target.in_(node_ids),
                )
            )
        )
    ).all()
    return [
        StructuralEdge(
            source_symbol=node_symbols.get(edge.source, "unknown"),
            target_symbol=node_symbols.get(edge.target, "unknown"),
            type=edge.type,
            strength=edge.strength,
            label=edge.label,
            propagation_direction=edge.propagation_direction,
        )
        for edge in edges
    ]
