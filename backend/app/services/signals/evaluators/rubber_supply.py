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
        display_title = event.title_zh or event.title
        display_summary = event.summary_zh or event.summary
        direction_zh = direction_label(event.direction)
        event_type_zh = event_type_label(event.event_type)
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
                    f"{event.source} 报道橡胶{event_type_zh}事件：{display_title}",
                    min(0.95, event.confidence),
                ),
                build_trigger_step(
                    2,
                    "origin_supply_mapping",
                    "将产区天气、政策或出口扰动映射到 NR -> RU 供应链。",
                    0.86,
                ),
                build_trigger_step(
                    3,
                    "verification_gate",
                    f"{event.source_count} 个来源，验证状态 {event.verification_status}。",
                    0.9 if event.source_count >= 2 else 0.65,
                ),
            ],
            related_assets=sorted(set(event.affected_symbols or [context.symbol1]) | {"RU", "NR"}),
            risk_items=[
                f"橡胶供应冲击对 RU/NR 方向为 {direction_zh}。",
                f"产区事件类型 {event_type_zh}，严重度 {event.severity}/5。",
                "扩大仓位前交叉检查 RU 期限结构与青岛保税区库存。",
            ],
            manual_check_items=[
                "确认产区原始报道以及是否影响割胶或出口流。",
                "检查青岛保税区库存与海南、云南收购价。",
                "把新闻作为单边信号前先比较 RU 与 NR 基差。",
            ],
            title=f"{context.symbol1} 橡胶供应冲击",
            summary=(
                f"{display_title} 经产区供应链对 RU/NR {direction_zh}："
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
