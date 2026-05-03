from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import CommodityNode, RelationshipEdge
from app.models.position import Position
from app.models.watchlist import Watchlist
from app.services.positions.threshold_modifier import normalize_symbol, symbols_from_position
from app.services.signals.watchlist import upsert_position_watchlist_entry

_FALLBACK_PROPAGATION: dict[str, tuple[str, ...]] = {
    "RU": ("NR", "BR"),
    "NR": ("RU", "BR"),
    "BR": ("RU", "NR"),
    "RB": ("HC", "I", "J", "JM"),
    "HC": ("RB", "I", "J"),
    "I": ("RB", "HC", "J", "JM"),
    "J": ("RB", "HC", "JM"),
    "JM": ("J", "RB", "HC"),
    "CU": ("AL", "ZN"),
    "AL": ("CU", "ZN"),
    "ZN": ("CU", "AL"),
    "SC": ("FU", "TA"),
    "FU": ("SC", "TA"),
}


@dataclass(frozen=True)
class PropagationNode:
    symbol: str
    category: str
    source: str
    relationship: str
    strength: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "category": self.category,
            "source": self.source,
            "relationship": self.relationship,
            "strength": self.strength,
        }


async def activate_position_propagation(
    session: AsyncSession,
    position: Position,
) -> list[PropagationNode]:
    primary_symbols = sorted(symbols_from_position(position))
    nodes_by_symbol: dict[str, PropagationNode] = {}

    for symbol in primary_symbols:
        category = infer_category_from_symbol(symbol)
        nodes_by_symbol[symbol] = PropagationNode(
            symbol=symbol,
            category=category,
            source=symbol,
            relationship="position",
            strength=1.0,
        )
        for node in await graph_neighbors(session, symbol):
            nodes_by_symbol[node.symbol] = node
        for related in _FALLBACK_PROPAGATION.get(symbol, ()):
            nodes_by_symbol.setdefault(
                related,
                PropagationNode(
                    symbol=related,
                    category=infer_category_from_symbol(related),
                    source=symbol,
                    relationship="fallback_chain",
                    strength=0.5,
                ),
            )

    nodes = sorted(nodes_by_symbol.values(), key=lambda node: (node.source != node.symbol, node.symbol))
    for node in nodes:
        await upsert_position_watchlist_entry(
            session,
            symbol1=node.symbol,
            category=node.category,
            custom_thresholds={
                "position_linked": True,
                "threshold_multiplier": 0.8 if node.relationship == "position" else 0.9,
                "source_position_id": str(position.id),
                "source_symbol": node.source,
                "relationship": node.relationship,
                "strength": node.strength,
            },
        )
    position.propagation_nodes = [node.to_dict() for node in nodes]
    await session.flush()
    return nodes


async def deactivate_position_propagation(session: AsyncSession, position: Position) -> int:
    symbols = {
        normalize_symbol(str(node.get("symbol")))
        for node in position.propagation_nodes or []
        if isinstance(node, dict)
    }
    symbols.update(symbols_from_position(position))
    symbols.discard(None)
    if not symbols:
        return 0

    protected = await active_position_symbols(session, exclude_position_id=position.id)
    rows = (
        await session.scalars(
            select(Watchlist).where(
                Watchlist.position_linked.is_(True),
                Watchlist.symbol1.in_(sorted(symbols - protected)),
            )
        )
    ).all()
    for row in rows:
        row.enabled = False
    await session.flush()
    return len(rows)


async def graph_neighbors(session: AsyncSession, symbol: str) -> list[PropagationNode]:
    source = (
        await session.scalars(
            select(CommodityNode).where(CommodityNode.symbol == symbol).limit(1)
        )
    ).first()
    if source is None:
        return []

    rows = (
        await session.execute(
            select(RelationshipEdge, CommodityNode)
            .join(
                CommodityNode,
                or_(
                    CommodityNode.id == RelationshipEdge.target,
                    CommodityNode.id == RelationshipEdge.source,
                ),
            )
            .where(
                or_(RelationshipEdge.source == source.id, RelationshipEdge.target == source.id),
                CommodityNode.id != source.id,
            )
            .order_by(RelationshipEdge.strength.desc())
            .limit(8)
        )
    ).all()
    return [
        PropagationNode(
            symbol=node.symbol,
            category=node.cluster,
            source=symbol,
            relationship=edge.type,
            strength=float(edge.strength or 0),
        )
        for edge, node in rows
    ]


async def active_position_symbols(
    session: AsyncSession,
    *,
    exclude_position_id,
) -> set[str]:
    rows = (
        await session.scalars(
            select(Position).where(Position.status == "open", Position.id != exclude_position_id)
        )
    ).all()
    symbols: set[str] = set()
    for row in rows:
        symbols.update(symbols_from_position(row))
        for node in row.propagation_nodes or []:
            if isinstance(node, dict):
                symbol = normalize_symbol(str(node.get("symbol") or ""))
                if symbol:
                    symbols.add(symbol)
    return symbols


def infer_category_from_symbol(symbol: str) -> str:
    root = "".join(char for char in symbol.upper() if char.isalpha())
    if root in {"RB", "HC", "I", "J", "JM", "SF", "SM"}:
        return "ferrous"
    if root in {"RU", "NR", "BR"}:
        return "rubber"
    if root in {"SC", "FU", "TA", "EG", "MA", "PP", "L", "V"}:
        return "energy"
    if root in {"CU", "AL", "ZN", "NI", "SN", "PB"}:
        return "nonferrous"
    if root in {"M", "Y", "P", "C", "A", "CF", "SR"}:
        return "agriculture"
    return "unknown"
