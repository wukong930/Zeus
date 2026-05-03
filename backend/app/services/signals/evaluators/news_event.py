from typing import Any

from app.services.news.quality import is_evaluable_news_event
from app.services.signals.helpers import build_trigger_step
from app.services.signals.outcomes import directional_outcome
from app.services.signals.types import (
    MarketBar,
    NewsEventPoint,
    OutcomeEvaluation,
    TriggerContext,
    TriggerResult,
)


class NewsEventEvaluator:
    signal_type = "news_event"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        candidates = [
            event
            for event in context.news_events
            if affects_symbol(event, context.symbol1)
            and is_evaluable_news_event(
                severity=event.severity,
                source_count=event.source_count,
                verification_status=event.verification_status,
            )
            and not event.requires_manual_confirmation
        ]
        if not candidates:
            return None

        event = max(
            candidates,
            key=lambda item: (item.severity, item.confidence, item.source_count),
        )
        severity = severity_label(event.severity)
        confidence = min(
            0.95,
            event.confidence * (0.55 + event.severity * 0.08) + min(0.08, event.source_count * 0.02),
        )
        direction_phrase = direction_to_phrase(event.direction)
        trigger_chain = [
            build_trigger_step(
                1,
                "news_event",
                f"{event.source} reported {event.event_type} event: {event.title}",
                min(0.95, event.confidence),
            ),
            build_trigger_step(
                2,
                "cross_source",
                f"{event.source_count} independent source(s); status {event.verification_status}.",
                0.9 if event.source_count >= 2 else 0.65,
            ),
            build_trigger_step(
                3,
                "impact_mapping",
                f"Mapped to {', '.join(event.affected_symbols)} as {event.direction}.",
                0.85 if event.direction in {"bullish", "bearish"} else 0.65,
            ),
        ]

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=confidence,
            trigger_chain=trigger_chain,
            related_assets=event.affected_symbols or [context.symbol1],
            risk_items=[
                f"{context.symbol1} {direction_phrase} due to {event.event_type} news.",
                f"Event severity {event.severity}/5, horizon {event.time_horizon}.",
                f"Source verification: {event.verification_status}.",
            ],
            manual_check_items=[
                "Confirm source independence and original announcement.",
                "Check whether the affected contract is liquid enough for immediate action.",
                "Review downstream transmission before upgrading to trade recommendation.",
            ],
            title=f"{context.symbol1} {event.event_type} news event",
            summary=(
                f"{event.title} Severity {event.severity}/5, {event.direction} for "
                f"{', '.join(event.affected_symbols or [context.symbol1])}: {event.summary}"
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


def affects_symbol(event: NewsEventPoint, symbol: str) -> bool:
    root = "".join(char for char in symbol.upper() if char.isalpha())
    affected = {"".join(char for char in item.upper() if char.isalpha()) for item in event.affected_symbols}
    return root in affected


def severity_label(severity: int) -> str:
    if severity >= 5:
        return "critical"
    if severity >= 4:
        return "high"
    if severity >= 3:
        return "medium"
    return "low"


def direction_to_phrase(direction: str) -> str:
    if direction == "bullish":
        return "bullish"
    if direction == "bearish":
        return "bearish"
    if direction == "mixed":
        return "mixed"
    return "unclear"
