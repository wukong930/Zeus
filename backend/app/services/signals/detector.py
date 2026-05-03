import asyncio

from app.services.signals.evaluators import MomentumEvaluator, SpreadAnomalyEvaluator
from app.services.signals.types import TriggerContext, TriggerEvaluator, TriggerResult


DEFAULT_EVALUATORS: tuple[TriggerEvaluator, ...] = (
    SpreadAnomalyEvaluator(),
    MomentumEvaluator(),
)


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
        results = await asyncio.gather(*(evaluator.evaluate(context) for evaluator in evaluators))
        return [result for result in results if result is not None]
