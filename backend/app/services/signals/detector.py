import asyncio

from app.services.signals.evaluators import (
    BasisShiftEvaluator,
    CapacityContractionEvaluator,
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
from app.services.signals.types import TriggerContext, TriggerEvaluator, TriggerResult


DEFAULT_EVALUATORS: tuple[TriggerEvaluator, ...] = (
    SpreadAnomalyEvaluator(),
    BasisShiftEvaluator(),
    MomentumEvaluator(),
    RegimeShiftEvaluator(),
    InventoryShockEvaluator(),
    PriceGapEvaluator(),
    NewsEventEvaluator(),
    CapacityContractionEvaluator(),
    RestartExpectationEvaluator(),
    MedianPressureEvaluator(),
    MarginalCapacitySqueezeEvaluator(),
    RubberSupplyShockEvaluator(),
)

ROLL_WINDOW_DEGRADED_SIGNALS = {"spread_anomaly", "basis_shift"}


class SignalDetector:
    def __init__(self, evaluators: tuple[TriggerEvaluator, ...] = DEFAULT_EVALUATORS) -> None:
        self._evaluators = evaluators

    async def detect(
        self,
        context: TriggerContext,
        *,
        signal_types: set[str] | None = None,
    ) -> list[TriggerResult]:
        evaluators = [
            evaluator
            for evaluator in self._evaluators
            if signal_types is None or evaluator.signal_type in signal_types
        ]
        if context.in_roll_window:
            evaluators = [
                evaluator
                for evaluator in evaluators
                if evaluator.signal_type not in ROLL_WINDOW_DEGRADED_SIGNALS
            ]
        results = await asyncio.gather(*(evaluator.evaluate(context) for evaluator in evaluators))
        return [result for result in results if result is not None]
