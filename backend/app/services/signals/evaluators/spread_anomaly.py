from app.services.signals.helpers import build_trigger_step, severity_from_z_score
from typing import Any

from app.services.positions.threshold_modifier import get_position_aware_thresholds
from app.services.signals.outcomes import outcome_result, pending_result, sorted_bars
from app.services.signals.types import MarketBar, OutcomeEvaluation, SpreadInfo, TriggerContext, TriggerResult


class SpreadAnomalyEvaluator:
    signal_type = "spread_anomaly"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if context.spread_stats is None or context.symbol2 is None:
            return None

        stats = context.spread_stats
        abs_z = abs(stats.current_z_score)
        thresholds = get_position_aware_thresholds(
            context.category,
            symbols=(context.symbol1, context.symbol2),
            half_life=stats.half_life,
        )
        if abs_z <= thresholds.z_score_entry:
            return None

        display_mean = stats.raw_spread_mean if stats.raw_spread_mean is not None else stats.spread_mean
        display_std = (
            stats.raw_spread_std_dev if stats.raw_spread_std_dev is not None else stats.spread_std_dev
        )
        current_spread = display_mean + stats.current_z_score * display_std
        stationarity_passed = stats.adf_p_value < 0.05
        half_life_fast = stats.half_life < 30

        trigger_chain = [
            build_trigger_step(
                1,
                "z_score_check",
                f"Spread z-score is {stats.current_z_score:.2f}.",
                0.95 if abs_z > 3 else 0.85 if abs_z > 2.5 else 0.75,
            ),
            build_trigger_step(
                2,
                "spread_distance",
                f"Current spread {current_spread:.2f}, mean {display_mean:.2f}, sigma {display_std:.2f}.",
                0.8,
            ),
            build_trigger_step(
                3,
                "stationarity",
                f"ADF p-value {stats.adf_p_value:.4f}; half-life {stats.half_life:.1f} days.",
                0.9 if stationarity_passed and half_life_fast else 0.7,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)

        spread_info = SpreadInfo(
            leg1=context.symbol1,
            leg2=context.symbol2,
            current_spread=current_spread,
            historical_mean=display_mean,
            sigma1_upper=display_mean + display_std,
            sigma1_lower=display_mean - display_std,
            z_score=stats.current_z_score,
            half_life=stats.half_life,
            adf_p_value=stats.adf_p_value,
            unit="price",
        )

        risk_items = [
            f"Spread z-score is {stats.current_z_score:.2f}.",
            "Stationarity check failed." if not stationarity_passed else "",
            f"Half-life is {stats.half_life:.1f} days." if not half_life_fast else "",
            "Confirm contract liquidity and roll-window effects.",
        ]

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity_from_z_score(stats.current_z_score),
            confidence=confidence,
            trigger_chain=trigger_chain,
            spread_info=spread_info,
            related_assets=[context.symbol1, context.symbol2],
            risk_items=[item for item in risk_items if item],
            manual_check_items=[
                "Confirm both legs have enough liquidity.",
                "Check for policy or exchange rule changes.",
                "Estimate transaction costs and slippage.",
            ],
            title=f"{context.symbol1}/{context.symbol2} spread anomaly",
            summary=(
                f"{context.symbol1}/{context.symbol2} spread z-score reached "
                f"{stats.current_z_score:.2f}; half-life is {stats.half_life:.1f} days."
            ),
        )

    def evaluate_outcome(
        self,
        signal: dict[str, Any],
        market_data: list[MarketBar],
        horizon_days: int,
    ) -> OutcomeEvaluation:
        spread_info = signal.get("spread_info")
        if not isinstance(spread_info, dict):
            return pending_result("Missing spread_info.", horizon_days, market_data)

        mean = float(spread_info["historical_mean"])
        sigma = abs(float(spread_info["sigma1_upper"]) - mean)
        if sigma <= 0:
            return pending_result("Spread sigma is zero.", horizon_days, market_data)

        ordered = sorted_bars(market_data, horizon_days)
        if not ordered:
            return pending_result("Not enough forward market data.", horizon_days, ordered)

        hit = any(abs((bar.close - mean) / sigma) <= 0.5 for bar in ordered)
        return outcome_result(
            outcome="hit" if hit else "miss",
            reason="Spread z-score reverted inside +/-0.5." if hit else "Spread did not revert.",
            horizon_days=horizon_days,
            market_data=ordered,
        )
