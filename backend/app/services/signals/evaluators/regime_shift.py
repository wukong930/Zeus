from statistics import mean

from app.services.signals.helpers import build_trigger_step, hurst_exponent, log_returns, std_dev
from app.services.signals.thresholds import get_thresholds
from app.services.signals.types import TriggerContext, TriggerResult


class RegimeShiftEvaluator:
    signal_type = "regime_shift"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if len(context.market_data) < 30:
            return None

        ordered = sorted(context.market_data, key=lambda bar: bar.timestamp)
        closes = [bar.close for bar in ordered]
        returns = log_returns(closes)
        if len(returns) < 20:
            return None

        thresholds = get_thresholds(context.category)
        recent_returns = returns[-10:]
        long_returns = returns[-30:-10] if len(returns) >= 30 else returns[:-10]
        if not long_returns:
            return None
        recent_vol = std_dev(recent_returns)
        long_vol = std_dev(long_returns)
        vol_ratio = recent_vol / long_vol if long_vol > 0 else 1.0
        volatility_regime = "high" if vol_ratio > 1.8 else "low" if vol_ratio < 0.55 else "normal"
        volatility_changed = volatility_regime != "normal"

        global_hurst = hurst_exponent(returns)
        recent_hurst = hurst_exponent(recent_returns)
        hurst_shifted = abs(recent_hurst - global_hurst) > thresholds.hurst_shift

        direction_shifted = False
        if len(returns) >= 30:
            direction_shifted = (mean(returns[-10:]) > 0) != (mean(returns[-30:-10]) > 0)

        if not volatility_changed and not hurst_shifted and not direction_shifted:
            return None

        trigger_chain = [
            build_trigger_step(
                1,
                "volatility_regime",
                f"Recent/long volatility ratio is {vol_ratio:.2f}; regime is {volatility_regime}.",
                0.85 if volatility_changed else 0.45,
            ),
            build_trigger_step(
                2,
                "hurst_shift",
                f"Hurst changed from {global_hurst:.2f} to {recent_hurst:.2f}.",
                0.8 if hurst_shifted else 0.5,
            ),
            build_trigger_step(
                3,
                "direction_shift",
                "Recent return direction differs from prior window."
                if direction_shifted
                else "Recent return direction is consistent.",
                0.75 if direction_shifted else 0.45,
            ),
        ]
        confidence = sum(step.confidence for step in trigger_chain) / len(trigger_chain)
        severity = "high" if vol_ratio > 2.2 else "medium" if volatility_changed or hurst_shifted else "low"

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=confidence,
            trigger_chain=trigger_chain,
            related_assets=[context.symbol1] if context.symbol2 is None else [context.symbol1, context.symbol2],
            risk_items=[
                f"Volatility regime is {volatility_regime} with ratio {vol_ratio:.2f}.",
                f"Hurst changed {global_hurst:.2f} -> {recent_hurst:.2f}." if hurst_shifted else "",
                "Return direction shifted across windows." if direction_shifted else "",
                "Mean-reversion assumptions may need review.",
            ],
            manual_check_items=[
                "Review current strategy suitability under the new regime.",
                "Check macro, policy, and liquidity context.",
                "Consider reducing position size until regime stabilizes.",
            ],
            title=f"{context.symbol1} regime shift",
            summary=(
                f"{context.symbol1} regime changed: vol ratio {vol_ratio:.2f}, "
                f"Hurst {global_hurst:.2f}->{recent_hurst:.2f}."
            ),
        )
