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
from app.services.translation.market import direction_label, event_type_label


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
        display_title = event.title_zh or event.title
        display_summary = event.summary_zh or event.summary
        event_type_zh = event_type_label(event.event_type)
        direction_zh = direction_label(event.direction)
        trigger_chain = [
            build_trigger_step(
                1,
                "news_event",
                f"{event.source} 报道{event_type_zh}事件：{display_title}",
                min(0.95, event.confidence),
            ),
            build_trigger_step(
                2,
                "cross_source",
                f"{event.source_count} 个独立来源；验证状态 {event.verification_status}。",
                0.9 if event.source_count >= 2 else 0.65,
            ),
            build_trigger_step(
                3,
                "impact_mapping",
                f"映射到 {', '.join(event.affected_symbols)}，方向 {direction_zh}。",
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
                f"{context.symbol1} 受到{event_type_zh}新闻影响，方向 {direction_zh}。",
                f"事件严重度 {event.severity}/5，影响窗口 {event.time_horizon}。",
                f"来源验证状态：{event.verification_status}。",
            ],
            manual_check_items=[
                "确认来源独立性和原始公告。",
                "检查受影响合约流动性是否支持即时行动。",
                "升级为交易建议前复核下游传导链路。",
            ],
            title=f"{context.symbol1} {event_type_zh}新闻事件",
            summary=(
                f"{display_title}。严重度 {event.severity}/5，"
                f"对 {', '.join(event.affected_symbols or [context.symbol1])} {direction_zh}："
                f"{display_summary}"
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
