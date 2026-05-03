from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.position import Position

STALE_WARNING_DAYS = 7
STALE_DEGRADE_DAYS = 14


@dataclass(frozen=True)
class FreshnessResult:
    scanned: int
    stale: int
    degraded: int
    position_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "stale": self.stale,
            "degraded": self.degraded,
            "position_ids": self.position_ids,
        }


async def check_position_freshness(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    warning_days: int = STALE_WARNING_DAYS,
    degrade_days: int = STALE_DEGRADE_DAYS,
) -> FreshnessResult:
    effective_at = as_of or datetime.now(timezone.utc)
    rows = (
        await session.scalars(
            select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
        )
    ).all()
    stale_count = 0
    degraded_count = 0
    affected: list[str] = []
    for row in rows:
        reference = row.last_updated_at or row.opened_at
        age = effective_at - reference
        if age >= timedelta(days=warning_days):
            stale_count += 1
            affected.append(str(row.id))
            if row.stale_since is None:
                row.stale_since = effective_at
        if age >= timedelta(days=degrade_days):
            degraded_count += 1
            row.data_mode = "stale_no_position"
        elif row.data_mode == "stale_no_position":
            row.data_mode = "position_aware"

    await session.flush()
    return FreshnessResult(
        scanned=len(rows),
        stale=stale_count,
        degraded=degraded_count,
        position_ids=affected,
    )
