from typing import Any

from app.services.signals.helpers import build_trigger_step, severity_from_z_score, volume_change
from app.services.signals.outcomes import directional_outcome
from app.services.signals.thresholds import get_thresholds
from app.services.signals.types import MarketBar, OutcomeEvaluation, SpreadInfo, TriggerContext, TriggerResult


class BasisShiftEvaluator:
    signal_type = "basis_shift"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if context.spread_stats is None or context.symbol2 is None:
            return None

        stats = context.spread_stats
        abs_z = abs(stats.current_z_score)
        volatility_regime = "high" if abs_z > 3.5 else "low" if abs_z < 1.5 else "normal"
        thresholds = get_thresholds(
            context.category,
            volatility_regime=volatility_regime,
            half_life=stats.half_life,
        )
        if abs_z <= thresholds.basis_deviation:
            return None

        ordered_desc = sorted(context.market_data, key=lambda bar: bar.timestamp, reverse=True)
        consecutive_days = 0
        for idx in range(min(5, max(0, len(ordered_desc) - 1))):
            day_return = ordered_desc[idx].close - ordered_desc[idx + 1].close
            same_direction = day_return > 0 if stats.current_z_score > 0 else day_return < 0
            if not same_direction:
                break
            consecutive_days += 1

        has_persistence = consecutive_days >= 3
        volume_delta = 0.0
        if len(ordered_desc) >= 2:
            volume_delta = volume_change(ordered_desc[0].volume, ordered_desc[1].volume)
        volume_confirmed = volume_delta > 20

        display_mean = stats.raw_spread_mean if stats.raw_spread_mean is not None else stats.spread_mean
        display_std = (
            stats.raw_spread_std_dev if stats.raw_spread_std_dev is not None else stats.spread_std_dev
        )
        current_spread = display_mean + stats.current_z_score * display_std

        trigger_chain = [
            build_trigger_step(
                1,
                "basis_deviation",
                f"Basis deviated {abs_z:.2f} sigma from its historical mean.",
                0.9 if abs_z > 2 else 0.75,
            ),
            build_trigger_step(
                2,
                "persistence",
                f"Persistence count is {consecutive_days} recent sessions.",
                0.85 if has_persistence else 0.6,
            ),
            build_trigger_step(
                3,
                "volume",
                f"Volume changed {volume_delta:.1f}%.",
                0.85 if volume_confirmed else 0.6,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity_from_z_score(stats.current_z_score),
            confidence=confidence,
            trigger_chain=trigger_chain,
            spread_info=SpreadInfo(
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
            ),
            related_assets=[context.symbol1, context.symbol2],
            risk_items=[
                f"Basis deviation is {abs_z:.2f} sigma.",
                "Persistence is not yet confirmed." if not has_persistence else "",
                "Volume did not expand enough." if not volume_confirmed else "",
                "Check policy, freight, FX, and delivery-cost changes.",
            ],
            manual_check_items=[
                "Validate spot and futures basis inputs.",
                "Check import/export policy and freight changes.",
                "Confirm the signal is not caused by contract roll effects.",
            ],
            title=f"{context.symbol1}/{context.symbol2} basis shift",
            summary=(
                f"{context.symbol1}/{context.symbol2} basis deviated {abs_z:.2f} sigma; "
                f"volume changed {volume_delta:.1f}%."
            ),
        )

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
        )
