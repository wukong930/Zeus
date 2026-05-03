from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.signal import SignalTrack
from app.services.market_data.pit import get_market_data_pit
from app.services.signals.evaluators import (
    BasisShiftEvaluator,
    CapacityContractionEvaluator,
    EventDrivenEvaluator,
    InventoryShockEvaluator,
    MarginalCapacitySqueezeEvaluator,
    MedianPressureEvaluator,
    MomentumEvaluator,
    NewsEventEvaluator,
    PriceGapEvaluator,
    RegimeShiftEvaluator,
    RestartExpectationEvaluator,
    RubberSupplyShockEvaluator,
    SpreadAnomalyEvaluator,
)
from app.services.signals.types import MarketBar, OutcomeEvaluation, TriggerEvaluator

DEFAULT_OUTCOME_HORIZONS: dict[str, int] = {
    "spread_anomaly": 20,
    "basis_shift": 14,
    "momentum": 20,
    "regime_shift": 30,
    "inventory_shock": 30,
    "event_driven": 5,
    "price_gap": 5,
    "news_event": 10,
    "rubber_supply_shock": 10,
    "capacity_contraction": 20,
    "restart_expectation": 20,
    "median_pressure": 10,
    "marginal_capacity_squeeze": 10,
}

DEFAULT_OUTCOME_EVALUATORS: dict[str, TriggerEvaluator] = {
    "spread_anomaly": SpreadAnomalyEvaluator(),
    "basis_shift": BasisShiftEvaluator(),
    "momentum": MomentumEvaluator(),
    "regime_shift": RegimeShiftEvaluator(),
    "inventory_shock": InventoryShockEvaluator(),
    "event_driven": EventDrivenEvaluator(),
    "price_gap": PriceGapEvaluator(),
    "news_event": NewsEventEvaluator(),
    "rubber_supply_shock": RubberSupplyShockEvaluator(),
    "capacity_contraction": CapacityContractionEvaluator(),
    "restart_expectation": RestartExpectationEvaluator(),
    "median_pressure": MedianPressureEvaluator(),
    "marginal_capacity_squeeze": MarginalCapacitySqueezeEvaluator(),
}


@dataclass(frozen=True)
class OutcomeScanResult:
    scanned: int
    resolved: int
    pending: int
    skipped: int


async def evaluate_pending_signals(
    session: AsyncSession,
    *,
    as_of: datetime | None = None,
    limit: int = 100,
    evaluators: dict[str, TriggerEvaluator] | None = None,
    horizons: dict[str, int] | None = None,
) -> OutcomeScanResult:
    effective_as_of = as_of or datetime.now(timezone.utc)
    evaluator_map = evaluators or DEFAULT_OUTCOME_EVALUATORS
    horizon_map = horizons or DEFAULT_OUTCOME_HORIZONS

    rows = (
        await session.scalars(
            select(SignalTrack)
            .where(SignalTrack.outcome == "pending")
            .order_by(SignalTrack.created_at.asc())
            .limit(limit)
        )
    ).all()

    scanned = 0
    resolved = 0
    pending = 0
    skipped = 0
    for row in rows:
        scanned += 1
        evaluator = evaluator_map.get(row.signal_type)
        horizon_days = horizon_map.get(row.signal_type, 20)
        if evaluator is None:
            skipped += 1
            continue

        alert = await session.get(Alert, row.alert_id) if row.alert_id is not None else None
        if alert is None:
            pending += 1
            continue

        start_at = alert.triggered_at or row.created_at
        due_at = start_at + timedelta(days=horizon_days)
        if effective_as_of < due_at:
            pending += 1
            continue

        signal = alert_to_signal_payload(alert, row)
        market_data = await load_forward_market_data(
            session,
            signal=signal,
            start_at=start_at,
            end_at=due_at,
            as_of=effective_as_of,
        )
        evaluation = evaluator.evaluate_outcome(signal, market_data, horizon_days)
        if evaluation.outcome == "pending":
            pending += 1
            continue

        apply_outcome(row, evaluation, resolved_at=effective_as_of)
        resolved += 1

    await session.flush()
    return OutcomeScanResult(scanned=scanned, resolved=resolved, pending=pending, skipped=skipped)


def alert_to_signal_payload(alert: Alert, signal_track: SignalTrack) -> dict[str, Any]:
    return {
        "signal_type": signal_track.signal_type,
        "category": signal_track.category,
        "confidence": signal_track.confidence,
        "related_assets": alert.related_assets,
        "spread_info": alert.spread_info,
        "risk_items": alert.risk_items,
        "manual_check_items": alert.manual_check_items,
        "title": alert.title,
        "summary": alert.summary,
    }


async def load_forward_market_data(
    session: AsyncSession,
    *,
    signal: dict[str, Any],
    start_at: datetime,
    end_at: datetime,
    as_of: datetime | None = None,
) -> list[MarketBar]:
    symbol = primary_symbol(signal)
    if symbol is None:
        return []

    rows = await get_market_data_pit(
        session,
        symbol=symbol,
        as_of=as_of,
        start=start_at,
        end=end_at,
        limit=1_000,
    )
    return [
        MarketBar(
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            open_interest=row.open_interest,
        )
        for row in sorted(rows, key=lambda item: item.timestamp)
    ]


def primary_symbol(signal: dict[str, Any]) -> str | None:
    related_assets = signal.get("related_assets") or []
    if related_assets:
        return str(related_assets[0])

    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("leg1") is not None:
        return str(spread_info["leg1"])
    return None


def apply_outcome(
    signal_track: SignalTrack,
    evaluation: OutcomeEvaluation,
    *,
    resolved_at: datetime,
) -> None:
    signal_track.outcome = evaluation.outcome
    signal_track.forward_return_1d = evaluation.forward_return_1d
    signal_track.forward_return_5d = evaluation.forward_return_5d
    signal_track.forward_return_20d = evaluation.forward_return_20d
    signal_track.resolved_at = resolved_at
