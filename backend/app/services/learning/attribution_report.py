from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.recommendation import Recommendation


@dataclass(frozen=True)
class AttributionSlice:
    label: str
    samples: int
    wins: int
    win_rate: float
    expected_pnl: float
    avg_mae: float
    avg_mfe: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class AttributionReport:
    period_start: date
    period_end: date
    total_recommendations: int
    closed_recommendations: int
    win_rate: float
    expected_pnl: float
    slices: dict[str, list[AttributionSlice]]
    risk_assessment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_recommendations": self.total_recommendations,
            "closed_recommendations": self.closed_recommendations,
            "win_rate": self.win_rate,
            "expected_pnl": self.expected_pnl,
            "slices": {
                key: [item.to_dict() for item in values]
                for key, values in self.slices.items()
            },
            "risk_assessment": self.risk_assessment,
        }


async def generate_attribution_report(
    session: AsyncSession,
    *,
    period_start: date,
    period_end: date,
) -> AttributionReport:
    start_dt = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc)
    rows = (
        await session.execute(
            select(Recommendation, Alert)
            .outerjoin(Alert, Recommendation.alert_id == Alert.id)
            .where(
                Recommendation.created_at >= start_dt,
                Recommendation.created_at < end_dt,
            )
            .order_by(Recommendation.created_at.desc())
        )
    ).all()
    records = [(recommendation, alert) for recommendation, alert in rows]
    closed = [
        (recommendation, alert)
        for recommendation, alert in records
        if recommendation.pnl_realized is not None or recommendation.actual_exit is not None
    ]
    pnl_values = [float(recommendation.pnl_realized or 0) for recommendation, _ in closed]
    wins = sum(1 for pnl in pnl_values if pnl > 0)

    return AttributionReport(
        period_start=period_start,
        period_end=period_end,
        total_recommendations=len(records),
        closed_recommendations=len(closed),
        win_rate=ratio(wins, len(closed)),
        expected_pnl=average(pnl_values),
        slices={
            "signal_type": grouped_slices(closed, lambda rec, alert: alert.type if alert else "unknown"),
            "category": grouped_slices(closed, lambda rec, alert: alert.category if alert else "unknown"),
            "season": grouped_slices(closed, lambda rec, alert: f"{rec.created_at.month:02d}月"),
            "holding_period": grouped_slices(
                closed,
                lambda rec, alert: holding_bucket(rec.holding_period_days),
            ),
            "entry_timing": grouped_slices(
                closed,
                lambda rec, alert: entry_timing_bucket(rec.created_at.hour),
            ),
        },
        risk_assessment=risk_assessment(closed),
    )


def grouped_slices(
    rows: list[tuple[Recommendation, Alert | None]],
    key_fn,
) -> list[AttributionSlice]:
    grouped: dict[str, list[Recommendation]] = {}
    for recommendation, alert in rows:
        grouped.setdefault(str(key_fn(recommendation, alert)), []).append(recommendation)
    slices = [
        build_slice(label, values)
        for label, values in grouped.items()
    ]
    return sorted(slices, key=lambda item: (-item.samples, item.label))


def build_slice(label: str, rows: list[Recommendation]) -> AttributionSlice:
    pnl_values = [float(row.pnl_realized or 0) for row in rows]
    wins = sum(1 for value in pnl_values if value > 0)
    return AttributionSlice(
        label=label,
        samples=len(rows),
        wins=wins,
        win_rate=ratio(wins, len(rows)),
        expected_pnl=average(pnl_values),
        avg_mae=average([float(row.mae or 0) for row in rows]),
        avg_mfe=average([float(row.mfe or 0) for row in rows]),
    )


def risk_assessment(rows: list[tuple[Recommendation, Alert | None]]) -> dict[str, Any]:
    recommendations = [row for row, _ in rows]
    mae_values = sorted(abs(float(row.mae or 0)) for row in recommendations)
    mfe_values = sorted(float(row.mfe or 0) for row in recommendations)
    return {
        "stop_loss": {
            "p50_mae": percentile(mae_values, 0.5),
            "p80_mae": percentile(mae_values, 0.8),
            "note": "report_only_no_parameter_change",
        },
        "take_profit": {
            "p50_mfe": percentile(mfe_values, 0.5),
            "p80_mfe": percentile(mfe_values, 0.8),
            "note": "report_only_no_parameter_change",
        },
    }


def holding_bucket(value: float | None) -> str:
    days = float(value or 0)
    if days <= 1:
        return "0-1d"
    if days <= 5:
        return "2-5d"
    if days <= 20:
        return "6-20d"
    return "20d+"


def entry_timing_bucket(hour: int) -> str:
    if hour < 11:
        return "open"
    if hour >= 14:
        return "close"
    return "midday"


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
    return round(values[idx], 4)
