from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ZeusEvent, publish
from app.models.position import Position
from app.services.learning.recommendation_attribution import update_recommendation_from_position
from app.services.positions.propagation_activator import (
    activate_position_propagation,
    deactivate_position_propagation,
)
from app.services.positions.risk_recalc import recalculate_position_risk
from app.services.positions.threshold_modifier import update_position_threshold_cache

EventPublisher = Callable[..., Awaitable[ZeusEvent]]


@dataclass(frozen=True)
class PositionEventResult:
    position_id: str
    action: str
    propagation_nodes: int
    risk: dict[str, Any]
    attribution_updated: bool


async def handle_position_changed(
    event: ZeusEvent,
    session: AsyncSession | None = None,
    *,
    publisher: EventPublisher = publish,
) -> ZeusEvent | None:
    if session is None:
        return None
    position_id = event.payload.get("position_id")
    if position_id is None:
        return None
    position = await session.get(Position, UUID(str(position_id)))
    if position is None:
        return None

    update_position_threshold_cache(position)
    if position.status == "open":
        nodes = await activate_position_propagation(session, position)
        propagation_count = len(nodes)
    else:
        propagation_count = await deactivate_position_propagation(session, position)

    attribution = await update_recommendation_from_position(session, position)
    risk = await recalculate_position_risk(session)

    return await publisher(
        "position.monitoring_updated",
        {
            "position_id": str(position.id),
            "action": event.payload.get("action") or "updated",
            "propagation_nodes": propagation_count,
            "risk": risk.to_dict(),
            "attribution_updated": attribution.updated,
            "recommendation_id": attribution.recommendation_id,
        },
        source="position-agent",
        correlation_id=event.correlation_id,
        session=session,
    )
