from app.services.signals.evaluators.price_gap import PriceGapEvaluator


class EventDrivenEvaluator(PriceGapEvaluator):
    """Backward-compatible alias for Causa's original gap + volume event proxy."""

    signal_type = "event_driven"
