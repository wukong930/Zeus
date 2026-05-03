from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.alert_agent import AlertAgentConfig


@dataclass(frozen=True)
class ConfidenceThresholds:
    auto: float = 0.85
    notify: float = 0.60


async def load_confidence_thresholds(session: AsyncSession | None) -> ConfidenceThresholds:
    if session is None:
        return ConfidenceThresholds()
    try:
        row = (
            await session.scalars(
                select(AlertAgentConfig)
                .where(AlertAgentConfig.key == "confidence_thresholds")
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return ConfidenceThresholds()
    if row is None:
        return ConfidenceThresholds()

    value = row.value or {}
    return ConfidenceThresholds(
        auto=float(value.get("auto", ConfidenceThresholds.auto)),
        notify=float(value.get("notify", ConfidenceThresholds.notify)),
    )
