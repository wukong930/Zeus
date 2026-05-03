from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    contract_month: str
    close: float


@dataclass(frozen=True)
class ContinuousPoint:
    timestamp: datetime
    contract_month: str
    raw_close: float
    adjusted_close: float
    adjustment: float


def build_back_adjusted_main_series(points: list[PricePoint]) -> list[ContinuousPoint]:
    if not points:
        return []

    ordered = sorted(points, key=lambda item: item.timestamp)
    adjustment = 0.0
    previous = ordered[0]
    continuous = [
        ContinuousPoint(
            timestamp=previous.timestamp,
            contract_month=previous.contract_month,
            raw_close=previous.close,
            adjusted_close=previous.close,
            adjustment=adjustment,
        )
    ]

    for point in ordered[1:]:
        if point.contract_month != previous.contract_month:
            adjustment += previous.close - point.close

        continuous.append(
            ContinuousPoint(
                timestamp=point.timestamp,
                contract_month=point.contract_month,
                raw_close=point.close,
                adjusted_close=point.close + adjustment,
                adjustment=adjustment,
            )
        )
        previous = point

    return continuous
