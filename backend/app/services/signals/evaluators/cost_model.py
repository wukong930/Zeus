from statistics import mean
from typing import Any

from app.services.signals.helpers import build_trigger_step
from app.services.signals.outcomes import directional_outcome
from app.services.signals.types import (
    CostSnapshotPoint,
    MarketBar,
    OutcomeEvaluation,
    TriggerContext,
    TriggerResult,
)


def symbol_cost_snapshots(context: TriggerContext) -> list[CostSnapshotPoint]:
    symbol = context.symbol1.upper()
    return sorted(
        (row for row in context.cost_snapshots if row.symbol.upper() == symbol),
        key=lambda row: row.timestamp,
    )


def effective_margin(row: CostSnapshotPoint) -> float | None:
    if row.profit_margin is not None:
        return row.profit_margin
    if row.current_price is None or row.current_price <= 0:
        return None
    return (row.current_price - row.total_unit_cost) / row.current_price


def price_gap_pct(price: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return (threshold - price) / threshold


class CostModelOutcomeMixin:
    def evaluate_outcome(
        self,
        signal: dict[str, Any],
        market_data: list[MarketBar],
        horizon_days: int,
    ) -> OutcomeEvaluation:
        return directional_outcome(
            signal=signal,
            market_data=market_data,
            horizon_days=horizon_days,
            min_abs_return=0.005,
        )


class CapacityContractionEvaluator(CostModelOutcomeMixin):
    signal_type = "capacity_contraction"
    min_consecutive_snapshots = 10
    margin_threshold = -0.05

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        snapshots = symbol_cost_snapshots(context)
        margins = [effective_margin(row) for row in snapshots]
        valid_margins = [margin for margin in margins if margin is not None]
        if len(valid_margins) < self.min_consecutive_snapshots:
            return None

        recent = valid_margins[-self.min_consecutive_snapshots :]
        if not all(margin < self.margin_threshold for margin in recent):
            return None

        latest = snapshots[-1]
        latest_margin = recent[-1]
        average_margin = mean(recent)
        severity = "critical" if average_margin < -0.10 else "high"
        confidence = min(0.95, 0.78 + abs(average_margin) * 2)

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=round(confidence, 4),
            trigger_chain=[
                build_trigger_step(
                    1,
                    "margin_persistence",
                    (
                        f"{context.symbol1} profit margin stayed below -5% for "
                        f"{self.min_consecutive_snapshots} cost snapshots."
                    ),
                    0.9,
                ),
                build_trigger_step(
                    2,
                    "cost_curve",
                    (
                        f"Latest unit cost {latest.total_unit_cost:.2f}; "
                        f"latest margin {latest_margin * 100:.2f}%."
                    ),
                    0.85,
                ),
                build_trigger_step(
                    3,
                    "capacity_risk",
                    f"Average margin over the window is {average_margin * 100:.2f}%.",
                    confidence,
                ),
            ],
            related_assets=[context.symbol1],
            risk_items=[
                "Bearish capacity contraction risk: negative margins may force output cuts.",
                f"Profit margin window average is {average_margin * 100:.2f}%.",
                "Validate operating-rate and inventory changes before trading the signal.",
            ],
            manual_check_items=[
                "Check blast furnace operating rates and mill maintenance notices.",
                "Confirm spot raw-material quotes used by the cost model.",
                "Look for policy or demand shocks that may override cost pressure.",
            ],
            title=f"{context.symbol1} capacity contraction risk",
            summary=(
                f"{context.symbol1} margins stayed below -5% for two trading weeks; "
                "bearish supply contraction pressure is building."
            ),
        )


class RestartExpectationEvaluator(CostModelOutcomeMixin):
    signal_type = "restart_expectation"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        snapshots = symbol_cost_snapshots(context)
        margins = [effective_margin(row) for row in snapshots]
        valid_margins = [margin for margin in margins if margin is not None]
        if len(valid_margins) < 3:
            return None

        latest_margin = valid_margins[-1]
        previous_margin = valid_margins[-2]
        previous_window = valid_margins[-6:-1] or valid_margins[:-1]
        if latest_margin <= 0 or not previous_window or min(previous_window) >= 0:
            return None
        if previous_margin > 0 and mean(previous_window) > -0.01:
            return None

        confidence = 0.82 if previous_margin < 0 else 0.74
        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity="medium" if latest_margin < 0.03 else "high",
            confidence=confidence,
            trigger_chain=[
                build_trigger_step(
                    1,
                    "margin_cross",
                    (
                        f"{context.symbol1} margin crossed from "
                        f"{previous_margin * 100:.2f}% to {latest_margin * 100:.2f}%."
                    ),
                    0.88,
                ),
                build_trigger_step(
                    2,
                    "restart_zone",
                    "Positive margin may support idle capacity restarts.",
                    confidence,
                ),
            ],
            related_assets=[context.symbol1],
            risk_items=[
                "Bullish restart expectation: margin recovery may improve production incentives.",
                "Higher operating rates can later cap upside if demand does not follow.",
            ],
            manual_check_items=[
                "Check mill restart announcements and operating-rate surveys.",
                "Validate whether spot demand confirms the margin recovery.",
            ],
            title=f"{context.symbol1} restart expectation",
            summary=(
                f"{context.symbol1} profit margin turned positive after a negative window; "
                "restart expectation signal triggered."
            ),
        )


class MedianPressureEvaluator(CostModelOutcomeMixin):
    signal_type = "median_pressure"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        snapshots = symbol_cost_snapshots(context)
        if not snapshots:
            return None
        latest = snapshots[-1]
        if latest.current_price is None or latest.current_price >= latest.breakeven_p50:
            return None

        gap = price_gap_pct(latest.current_price, latest.breakeven_p50)
        margin = effective_margin(latest)
        severity = "high" if gap > 0.04 or (margin is not None and margin < -0.05) else "medium"
        confidence = min(0.9, 0.72 + gap * 3)

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=round(confidence, 4),
            trigger_chain=[
                build_trigger_step(
                    1,
                    "p50_breach",
                    (
                        f"Price {latest.current_price:.2f} is below P50 breakeven "
                        f"{latest.breakeven_p50:.2f}."
                    ),
                    0.86,
                ),
                build_trigger_step(
                    2,
                    "median_cost_pressure",
                    f"Price is {gap * 100:.2f}% below the median cost curve.",
                    confidence,
                ),
            ],
            related_assets=[context.symbol1],
            risk_items=[
                "Bearish median cost pressure: price is below the P50 cost curve.",
                "A sustained breach implies broad producer margin stress.",
            ],
            manual_check_items=[
                "Check whether the latest traded contract is distorted by roll-window liquidity.",
                "Verify spot basis and raw-material quotes.",
            ],
            title=f"{context.symbol1} median cost pressure",
            summary=(
                f"{context.symbol1} price fell below P50 breakeven; "
                "median cost pressure signal triggered."
            ),
        )


class MarginalCapacitySqueezeEvaluator(CostModelOutcomeMixin):
    signal_type = "marginal_capacity_squeeze"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        snapshots = symbol_cost_snapshots(context)
        if not snapshots:
            return None
        latest = snapshots[-1]
        if latest.current_price is None or latest.current_price >= latest.breakeven_p90:
            return None

        threshold = latest.breakeven_p75 if latest.current_price < latest.breakeven_p75 else latest.breakeven_p90
        tier = "P75" if latest.current_price < latest.breakeven_p75 else "P90"
        gap = price_gap_pct(latest.current_price, threshold)
        severity = "high" if tier == "P75" else "medium"
        confidence = min(0.88, 0.68 + gap * 2.5)

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=round(confidence, 4),
            trigger_chain=[
                build_trigger_step(
                    1,
                    "marginal_breach",
                    (
                        f"Price {latest.current_price:.2f} is below {tier} breakeven "
                        f"{threshold:.2f}."
                    ),
                    0.84 if tier == "P75" else 0.74,
                ),
                build_trigger_step(
                    2,
                    "capacity_squeeze",
                    f"Marginal capacity is squeezed by {gap * 100:.2f}%.",
                    confidence,
                ),
            ],
            related_assets=[context.symbol1],
            risk_items=[
                f"Bearish marginal squeeze: price is below {tier} cost support.",
                "High-cost capacity may reduce runs if spot prices remain below breakeven.",
            ],
            manual_check_items=[
                "Check whether high-cost producers are already cutting operating rates.",
                "Compare public cost model output with industry spot breakeven commentary.",
            ],
            title=f"{context.symbol1} marginal capacity squeeze",
            summary=(
                f"{context.symbol1} price is below {tier} breakeven; "
                "marginal capacity squeeze signal triggered."
            ),
        )
