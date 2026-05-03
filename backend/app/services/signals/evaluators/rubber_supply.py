from typing import Any

from app.services.news.quality import is_evaluable_news_event
from app.services.signals.evaluators.news_event import direction_to_phrase
from app.services.signals.helpers import build_trigger_step
from app.services.signals.outcomes import directional_outcome
from app.services.signals.types import (
    MarketBar,
    NewsEventPoint,
    OutcomeEvaluation,
    TriggerContext,
    TriggerResult,
)

RUBBER_SYMBOLS = {"RU", "NR", "BR"}
RUBBER_EVENT_TYPES = {"weather", "supply", "policy"}
RUBBER_ORIGIN_MARKERS = (
    "thailand",
    "thai",
    "indonesia",
    "malaysia",
    "vietnam",
    "hainan",
    "yunnan",
    "qingdao",
    "泰国",
    "印尼",
    "印度尼西亚",
    "马来西亚",
    "越南",
    "海南",
    "云南",
    "青岛",
)
SUPPLY_STRESS_MARKERS = (
    "flood",
    "rain",
    "rainfall",
    "storm",
    "drought",
    "monsoon",
    "export",
    "tariff",
    "policy",
    "tapping",
    "supply",
    "暴雨",
    "洪水",
    "降雨",
    "台风",
    "干旱",
    "出口",
    "关税",
    "政策",
    "割胶",
    "停割",
    "供应",
)


class RubberSupplyShockEvaluator:
    signal_type = "rubber_supply_shock"

    async def evaluate(self, context: TriggerContext) -> TriggerResult | None:
        if symbol_root(context.symbol1) not in RUBBER_SYMBOLS and context.category != "rubber":
            return None

        candidates = [
            event
            for event in context.news_events
            if is_rubber_supply_event(event, context.symbol1)
            and is_evaluable_news_event(
                severity=event.severity,
                source_count=event.source_count,
                verification_status=event.verification_status,
            )
            and not event.requires_manual_confirmation
        ]
        if not candidates:
            return None

        event = max(candidates, key=lambda item: (item.severity, item.confidence, item.source_count))
        direction_phrase = direction_to_phrase(event.direction)
        confidence = min(
            0.94,
            0.68 + event.severity * 0.04 + min(0.1, event.source_count * 0.025),
        )
        severity = "critical" if event.severity >= 5 else "high"

        return TriggerResult(
            signal_type=self.signal_type,
            triggered=True,
            severity=severity,
            confidence=round(confidence, 4),
            trigger_chain=[
                build_trigger_step(
                    1,
                    "rubber_origin_event",
                    f"{event.source} reported rubber {event.event_type}: {event.title}",
                    min(0.95, event.confidence),
                ),
                build_trigger_step(
                    2,
                    "origin_supply_mapping",
                    "Mapped origin weather/policy/export disruption to NR -> RU supply chain.",
                    0.86,
                ),
                build_trigger_step(
                    3,
                    "verification_gate",
                    f"{event.source_count} source(s), status {event.verification_status}.",
                    0.9 if event.source_count >= 2 else 0.65,
                ),
            ],
            related_assets=sorted(set(event.affected_symbols or [context.symbol1]) | {"RU", "NR"}),
            risk_items=[
                f"Rubber supply shock is {direction_phrase} for RU/NR.",
                f"Origin event type {event.event_type}, severity {event.severity}/5.",
                "Cross-check RU term structure and Qingdao bonded inventory before upgrading sizing.",
            ],
            manual_check_items=[
                "Confirm original origin-market report and whether it affects tapping/export flow.",
                "Check Qingdao bonded inventory and domestic Hainan/Yunnan collection prices.",
                "Compare RU and NR basis before treating the news as an outright signal.",
            ],
            title=f"{context.symbol1} rubber supply shock",
            summary=(
                f"{event.title} {event.direction} for RU/NR via origin supply chain: "
                f"{event.summary}"
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
            min_abs_return=0.006,
        )


def is_rubber_supply_event(event: NewsEventPoint, symbol: str) -> bool:
    affected = {symbol_root(item) for item in event.affected_symbols}
    if symbol_root(symbol) not in RUBBER_SYMBOLS and not (affected & RUBBER_SYMBOLS):
        return False
    if event.event_type not in RUBBER_EVENT_TYPES:
        return False
    text = f"{event.title} {event.summary}".lower()
    has_origin = any(marker in text for marker in RUBBER_ORIGIN_MARKERS)
    has_supply_marker = any(marker in text for marker in SUPPLY_STRESS_MARKERS)
    return has_origin or has_supply_marker


def symbol_root(symbol: str) -> str:
    return "".join(char for char in symbol.upper() if char.isalpha())
