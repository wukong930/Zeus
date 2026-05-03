import math

from app.services.signals.helpers import build_trigger_step, moving_average, volume_change
from app.services.signals.types import TriggerContext, TriggerResult


class MomentumEvaluator:
    signal_type = "momentum"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if len(context.market_data) < 21:
            return None

        ordered = sorted(context.market_data, key=lambda bar: bar.timestamp)
        close_prices = [bar.close for bar in ordered]
        volumes = [bar.volume for bar in ordered]
        ma5 = moving_average(close_prices, 5)
        ma20 = moving_average(close_prices, 20)

        current_idx = len(close_prices) - 1
        previous_idx = current_idx - 1
        if any(
            math.isnan(value)
            for value in (
                ma5[current_idx],
                ma20[current_idx],
                ma5[previous_idx],
                ma20[previous_idx],
            )
        ):
            return None

        bullish_cross = ma5[previous_idx] <= ma20[previous_idx] and ma5[current_idx] > ma20[current_idx]
        bearish_cross = ma5[previous_idx] >= ma20[previous_idx] and ma5[current_idx] < ma20[current_idx]
        if not bullish_cross and not bearish_cross:
            return None

        direction = "bullish" if bullish_cross else "bearish"
        current_price = close_prices[current_idx]
        recent_prices = close_prices[max(0, current_idx - 10) : current_idx]
        recent_high = max(recent_prices)
        recent_low = min(recent_prices)
        price_breakout = current_price > recent_high if bullish_cross else current_price < recent_low
        volume_delta = volume_change(volumes[current_idx], volumes[previous_idx])
        volume_confirmed = volume_delta > 30

        trigger_chain = [
            build_trigger_step(
                1,
                "moving_average",
                f"MA5 {ma5[current_idx]:.2f}; MA20 {ma20[current_idx]:.2f}.",
                0.8,
            ),
            build_trigger_step(
                2,
                "crossover",
                f"MA5 crossed {'above' if bullish_cross else 'below'} MA20.",
                0.85,
            ),
            build_trigger_step(
                3,
                "volume",
                f"Volume changed {volume_delta:.1f}%.",
                0.85 if volume_confirmed else 0.65,
            ),
            build_trigger_step(
                4,
                "breakout",
                f"Price {current_price:.2f} {'confirmed' if price_breakout else 'did not confirm'} breakout.",
                0.9 if price_breakout else 0.7,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)

        if volume_confirmed and price_breakout:
            severity = "high"
        elif volume_confirmed or price_breakout:
            severity = "medium"
        else:
            severity = "low"

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=confidence,
            trigger_chain=trigger_chain,
            related_assets=[context.symbol1],
            risk_items=[
                f"{direction.title()} moving-average crossover.",
                "Volume did not expand enough." if not volume_confirmed else "",
                "Price breakout is not confirmed." if not price_breakout else "",
                "Validate against current fundamental context.",
            ],
            manual_check_items=[
                "Check for event catalysts.",
                "Confirm trend is not driven by illiquid prints.",
                "Review nearby support and resistance.",
            ],
            title=f"{context.symbol1} momentum signal",
            summary=(
                f"{context.symbol1} generated a {direction} MA5/MA20 crossover; "
                f"volume changed {volume_delta:.1f}%."
            ),
        )
