from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.calibration.tracker import get_calibration_weight

CalibrationStrategy = Literal["pit", "frozen", "current"]
WeightLoader = Callable[..., Awaitable[float]]

CURRENT_WARNING = "current calibration uses future information and is not decision-grade"


@dataclass(frozen=True, slots=True)
class CalibrationReplayMetadata:
    calibration_strategy: CalibrationStrategy
    lookup_time: datetime
    warning: str | None = None

    def to_dict(self) -> dict:
        return {
            "calibration_strategy": self.calibration_strategy,
            "lookup_time": self.lookup_time.isoformat(),
            "warning": self.warning,
            "decision_grade": self.warning is None,
        }


def calibration_lookup_time(
    *,
    strategy: CalibrationStrategy = "pit",
    signal_time: datetime,
    backtest_start: datetime,
    current_time: datetime | None = None,
) -> datetime:
    if strategy == "pit":
        return _aware(signal_time)
    if strategy == "frozen":
        return _aware(backtest_start)
    if strategy == "current":
        return _aware(current_time or datetime.now(timezone.utc))
    raise ValueError(f"Unsupported calibration strategy: {strategy}")


def calibration_metadata(
    *,
    strategy: CalibrationStrategy = "pit",
    signal_time: datetime,
    backtest_start: datetime,
    current_time: datetime | None = None,
) -> CalibrationReplayMetadata:
    lookup_time = calibration_lookup_time(
        strategy=strategy,
        signal_time=signal_time,
        backtest_start=backtest_start,
        current_time=current_time,
    )
    return CalibrationReplayMetadata(
        calibration_strategy=strategy,
        lookup_time=lookup_time,
        warning=CURRENT_WARNING if strategy == "current" else None,
    )


async def replay_calibration_weight(
    session: AsyncSession | None,
    *,
    signal_type: str,
    category: str,
    regime: str | None,
    signal_time: datetime,
    backtest_start: datetime,
    strategy: CalibrationStrategy = "pit",
    current_time: datetime | None = None,
    loader: WeightLoader = get_calibration_weight,
) -> tuple[float, CalibrationReplayMetadata]:
    metadata = calibration_metadata(
        strategy=strategy,
        signal_time=signal_time,
        backtest_start=backtest_start,
        current_time=current_time,
    )
    weight = await loader(
        session,
        signal_type=signal_type,
        category=category,
        regime=regime,
        as_of=metadata.lookup_time,
    )
    return weight, metadata


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
