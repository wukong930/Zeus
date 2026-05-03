from statistics import mean
from typing import Any

from app.services.signals.helpers import build_trigger_step, log_returns, std_dev
from app.services.signals.outcomes import range_expansion_outcome
from app.services.signals.types import MarketBar, OutcomeEvaluation, TriggerContext, TriggerResult


class InventoryShockEvaluator:
    signal_type = "inventory_shock"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if len(context.market_data) < 10:
            return None

        ordered = sorted(context.market_data, key=lambda bar: bar.timestamp)
        range_ratios = [(bar.high - bar.low) / bar.close for bar in ordered if bar.close > 0]
        if len(range_ratios) < 10:
            return None

        recent_range = range_ratios[-5:]
        historical_range = range_ratios[-15:-5] or range_ratios[:-5]
        if not historical_range:
            return None
        range_ratio = mean(recent_range) / mean(historical_range) if mean(historical_range) > 0 else 1.0

        closes = [bar.close for bar in ordered]
        returns = log_returns(closes)
        recent_returns = returns[-5:]
        historical_returns = returns[-15:-5] or returns[:-5]
        if not historical_returns:
            return None
        recent_vol = std_dev(recent_returns)
        historical_vol = std_dev(historical_returns)
        vol_ratio = recent_vol / historical_vol if historical_vol > 0 else 1.0

        inventory_change_ratio = 0.0
        inventory_detected = False
        if len(context.inventory) >= 5:
            inventory = sorted(context.inventory, key=lambda point: point.timestamp)
            recent_inventory = inventory[-3:]
            earlier_inventory = inventory[-8:-3] or inventory[:-3]
            if earlier_inventory:
                recent_avg = mean(point.value for point in recent_inventory)
                earlier_avg = mean(point.value for point in earlier_inventory)
                inventory_change_ratio = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0.0
                inventory_detected = abs(inventory_change_ratio) > 0.15

        range_triggered = range_ratio > 1.8
        vol_triggered = vol_ratio > 1.6
        inventory_triggered = inventory_detected or (range_triggered and vol_triggered)
        spread_unstable = bool(
            context.spread_stats and abs(context.spread_stats.current_z_score) > 1.5
        )

        if not inventory_triggered and not range_triggered and not vol_triggered:
            return None

        trigger_chain = [
            build_trigger_step(
                1,
                "inventory",
                f"Inventory change ratio is {inventory_change_ratio * 100:.1f}%."
                if context.inventory
                else f"Range proxy ratio is {range_ratio:.2f}x.",
                0.9 if inventory_detected else 0.8 if range_triggered else 0.4,
            ),
            build_trigger_step(
                2,
                "volatility",
                f"Volatility ratio is {vol_ratio:.2f}x.",
                0.8 if vol_triggered else 0.35,
            ),
            build_trigger_step(
                3,
                "spread_stability",
                "Spread is unstable." if spread_unstable else "Spread is not materially unstable.",
                0.75 if spread_unstable else 0.5,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)
        severity = "high" if inventory_triggered else "medium" if range_triggered else "low"

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=confidence,
            trigger_chain=trigger_chain,
            related_assets=[context.symbol1],
            risk_items=[
                f"Range ratio expanded {range_ratio:.2f}x." if range_triggered else "",
                f"Volatility rose {vol_ratio:.2f}x." if vol_triggered else "",
                f"Inventory changed {inventory_change_ratio * 100:.1f}%." if inventory_detected else "",
                "Verify latest inventory and operating-rate data.",
            ],
            manual_check_items=[
                "Check latest warehouse and port inventory data.",
                "Review upstream/downstream operating rates.",
                "Assess whether inventory shock is temporary or structural.",
            ],
            title=f"{context.symbol1} inventory shock",
            summary=(
                f"{context.symbol1} inventory shock signal: range {range_ratio:.2f}x, "
                f"volatility {vol_ratio:.2f}x."
            ),
        )

    def evaluate_outcome(
        self,
        signal: dict[str, Any],
        market_data: list[MarketBar],
        horizon_days: int,
    ) -> OutcomeEvaluation:
        return range_expansion_outcome(market_data=market_data, horizon_days=horizon_days)
