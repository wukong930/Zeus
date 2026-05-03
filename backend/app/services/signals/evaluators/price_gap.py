from statistics import mean
from typing import Any

from app.services.signals.helpers import build_trigger_step
from app.services.signals.outcomes import directional_outcome
from app.services.signals.types import MarketBar, OutcomeEvaluation, TriggerContext, TriggerResult


class PriceGapEvaluator:
    signal_type = "price_gap"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if len(context.market_data) < 5:
            return None

        ordered = sorted(context.market_data, key=lambda bar: bar.timestamp)
        latest = ordered[-1]
        previous = ordered[-2]
        if previous.close == 0:
            return None

        gap_pct = abs((latest.close - previous.close) / previous.close) * 100
        recent = ordered[-min(20, len(ordered)) :]
        avg_daily_range_pct = mean((bar.high - bar.low) / bar.close for bar in recent if bar.close > 0) * 100
        gap_threshold = max(3.0, avg_daily_range_pct * 2.5)

        avg_volume = mean(bar.volume for bar in recent)
        volume_spike_pct = ((latest.volume - avg_volume) / avg_volume) * 100 if avg_volume > 0 else 0.0
        gap_triggered = gap_pct > gap_threshold
        volume_triggered = volume_spike_pct > 30

        if not gap_triggered and not volume_triggered:
            return None

        combined = gap_triggered and volume_triggered
        direction = "up" if latest.close > previous.close else "down"
        trigger_chain = [
            build_trigger_step(
                1,
                "price_gap",
                f"Close moved {direction} from {previous.close:.2f} to {latest.close:.2f}; gap {gap_pct:.2f}%.",
                0.9 if gap_triggered else 0.3,
            ),
            build_trigger_step(
                2,
                "volume_spike",
                f"Volume spike is {volume_spike_pct:.1f}% versus recent average.",
                0.85 if volume_triggered else 0.4,
            ),
            build_trigger_step(
                3,
                "event_proxy",
                "Gap and volume both triggered." if combined else "Single price-gap proxy triggered.",
                0.9 if combined else 0.7,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)
        severity = "high" if combined or gap_pct > 5 else "medium" if gap_triggered else "low"

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=confidence,
            trigger_chain=trigger_chain,
            related_assets=[context.symbol1],
            risk_items=[
                f"Price gap {gap_pct:.2f}% {direction}.",
                f"Volume spike {volume_spike_pct:.1f}%." if volume_triggered else "",
                "Technical price-gap proxy may be reacting to an external catalyst.",
            ],
            manual_check_items=[
                "Check news, policy announcements, and exchange notices.",
                "Confirm liquidity around the move.",
                "Assess whether the catalyst has durable fundamental impact.",
            ],
            title=f"{context.symbol1} price-gap signal",
            summary=(
                f"{context.symbol1} moved {gap_pct:.2f}% with volume spike "
                f"{volume_spike_pct:.1f}%; price-gap proxy triggered."
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
