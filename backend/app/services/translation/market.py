from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.registry import complete_with_llm_controls
from app.services.llm.types import LLMCompletionOptions, LLMConfigurationError, LLMMessage

TRANSLATION_PROMPT_VERSION = "market-translation-v1"
GLOSSARY_VERSION = "commodity-glossary-v4"
TRANSLATION_MODULE = "translation"


@dataclass(frozen=True)
class TranslationResult:
    title_original: str
    summary_original: str
    title_zh: str
    summary_zh: str
    source_language: str
    translation_status: str
    translation_model: str
    translation_prompt_version: str
    translation_glossary_version: str
    translated_at: datetime

    def to_model_fields(self) -> dict[str, Any]:
        return {
            "title_original": self.title_original,
            "summary_original": self.summary_original,
            "title_zh": self.title_zh,
            "summary_zh": self.summary_zh,
            "source_language": self.source_language,
            "translation_status": self.translation_status,
            "translation_model": self.translation_model,
            "translation_prompt_version": self.translation_prompt_version,
            "translation_glossary_version": self.translation_glossary_version,
            "translated_at": self.translated_at,
        }


TERM_PAIRS: tuple[tuple[str, str], ...] = (
    ("natural rubber", "天然橡胶"),
    ("rubber tapping", "割胶"),
    ("tapping", "割胶"),
    ("crude oil", "原油"),
    ("production cuts", "减产"),
    ("production drops", "产量下降"),
    ("production declines", "产量下降"),
    ("capacity squeeze", "产能挤压"),
    ("marginal capacity squeeze", "边际产能挤压"),
    ("high-cost capacity", "高成本产能"),
    ("High-cost capacity faces pressure to curtail runs", "高成本产能面临降低开工压力"),
    ("curtail runs", "降低开工"),
    ("breakeven", "盈亏平衡线"),
    ("supply chain", "供应链"),
    ("supply shock", "供应冲击"),
    ("weather", "天气"),
    ("rainfall", "降雨"),
    ("heavy rain", "强降雨"),
    ("floods", "洪水"),
    ("flood", "洪水"),
    ("drought", "干旱"),
    ("storm", "风暴"),
    ("monsoon", "季风"),
    ("tariff", "关税"),
    ("policy", "政策"),
    ("exports", "出口"),
    ("export", "出口"),
    ("imports", "进口"),
    ("inventory", "库存"),
    ("port congestion", "港口拥堵"),
    ("shipping", "航运"),
    ("logistics", "物流"),
    ("geopolitical", "地缘政治"),
    ("risk appetite", "风险偏好"),
    ("price", "价格"),
    ("prices", "价格"),
    ("price at", "价格位于"),
    ("is below", "低于"),
    ("is above", "高于"),
    ("remains below", "仍低于"),
    ("below", "低于"),
    ("above", "高于"),
    ("triggering", "触发"),
    ("triggering a", "触发"),
    ("medium-severity", "中等严重度"),
    ("high-severity", "高严重度"),
    ("low-severity", "低严重度"),
    ("spot remains", "现货仍"),
    ("spot", "现货"),
    ("faces pressure", "面临压力"),
    ("pct", "%"),
    ("in Q1", "一季度"),
    ("Q1", "一季度"),
    ("Q2", "二季度"),
    ("Q3", "三季度"),
    ("Q4", "四季度"),
    ("Xinhua", "新华社"),
    ("Reuters", "路透社"),
    ("Bloomberg", "彭博"),
    ("reported", "报道"),
    ("while", "同时"),
    ("with", "伴随"),
    ("of", "的"),
    ("to", "至"),
    ("extends", "延长"),
    ("drops", "下降"),
    ("drop", "下降"),
    ("declines", "下降"),
    ("rises", "上涨"),
    ("rise", "上涨"),
    ("bullish", "偏多"),
    ("bearish", "偏空"),
    ("mixed", "多空混合"),
    ("unclear", "不明确"),
    ("supply", "供应"),
    ("demand", "需求"),
    ("energy", "能源"),
    ("ferrous", "黑色系"),
    ("rubber", "橡胶"),
    ("metals", "有色金属"),
    ("agriculture", "农产品"),
    ("agri", "农产品"),
    ("OPEC+", "OPEC+"),
    ("Thailand", "泰国"),
    ("Thai", "泰国"),
    ("Indonesia", "印尼"),
    ("Malaysia", "马来西亚"),
    ("Vietnam", "越南"),
    ("China", "中国"),
    ("United States", "美国"),
    ("US", "美国"),
    ("Iran", "伊朗"),
    ("Middle East", "中东"),
    ("Qingdao", "青岛"),
    ("Hainan", "海南"),
    ("Yunnan", "云南"),
    ("PTA", "PTA"),
    ("PVC", "PVC"),
    ("copper", "铜"),
    ("aluminum", "铝"),
    ("zinc", "锌"),
    ("nickel", "镍"),
    ("iron ore", "铁矿石"),
    ("rebar", "螺纹钢"),
    ("hot rolled coil", "热卷"),
    ("coke", "焦炭"),
    ("coking coal", "焦煤"),
    ("soybean meal", "豆粕"),
    ("soybean oil", "豆油"),
    ("palm oil", "棕榈油"),
    ("gold", "黄金"),
    ("silver", "白银"),
)

SYMBOL_LABELS: dict[str, str] = {
    "RB": "螺纹钢",
    "HC": "热卷",
    "I": "铁矿石",
    "J": "焦炭",
    "JM": "焦煤",
    "RU": "天然橡胶",
    "NR": "20号胶",
    "BR": "顺丁橡胶",
    "SC": "原油",
    "TA": "PTA",
    "MA": "甲醇",
    "PP": "聚丙烯",
    "CU": "铜",
    "AL": "铝",
    "ZN": "锌",
    "NI": "镍",
    "M": "豆粕",
    "Y": "豆油",
    "P": "棕榈油",
    "AU": "黄金",
    "AG": "白银",
}

EVENT_TYPE_LABELS = {
    "policy": "政策",
    "supply": "供应",
    "demand": "需求",
    "inventory": "库存",
    "geopolitical": "地缘政治",
    "weather": "天气",
    "breaking": "突发",
}

DIRECTION_LABELS = {
    "bullish": "偏多",
    "bearish": "偏空",
    "mixed": "多空混合",
    "unclear": "不明确",
    "watch": "观察",
}

SEVERITY_LABELS = {
    "critical": "极高",
    "high": "高",
    "medium": "中",
    "low": "低",
}


def translate_market_text_pair(title: str, summary: str | None = None) -> TranslationResult:
    title_text = str(title or "").strip()
    summary_text = str(summary or title_text).strip() or title_text
    combined = f"{title_text}\n{summary_text}"
    source_language = detect_language(combined)
    translated_at = datetime.now(timezone.utc)
    if source_language == "zh":
        return TranslationResult(
            title_original=title_text,
            summary_original=summary_text,
            title_zh=title_text,
            summary_zh=summary_text,
            source_language=source_language,
            translation_status="source_zh",
            translation_model="source",
            translation_prompt_version=TRANSLATION_PROMPT_VERSION,
            translation_glossary_version=GLOSSARY_VERSION,
            translated_at=translated_at,
        )

    return TranslationResult(
        title_original=title_text,
        summary_original=summary_text,
        title_zh=glossary_translate(title_text),
        summary_zh=glossary_translate(summary_text),
        source_language=source_language,
        translation_status="glossary",
        translation_model="local-glossary",
        translation_prompt_version=TRANSLATION_PROMPT_VERSION,
        translation_glossary_version=GLOSSARY_VERSION,
        translated_at=translated_at,
    )


async def translate_market_text_pair_with_llm(
    session: AsyncSession | None,
    *,
    title: str,
    summary: str | None = None,
    use_llm: bool = False,
) -> TranslationResult:
    fallback = translate_market_text_pair(title, summary)
    if not use_llm or fallback.source_language == "zh":
        return fallback

    try:
        result = await complete_with_llm_controls(
            module=TRANSLATION_MODULE,
            session=session,
            options=LLMCompletionOptions(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "你是商品期货新闻翻译器。把英文市场新闻翻译成简洁中文，"
                            "保留合约代码、公司名、机构名和关键数字。不要补充原文没有的信息。"
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "title": fallback.title_original,
                                "summary": fallback.summary_original,
                                "glossary_version": GLOSSARY_VERSION,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
                temperature=0.0,
                max_tokens=700,
                json_mode=True,
                json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title_zh": {"type": "string"},
                        "summary_zh": {"type": "string"},
                    },
                    "required": ["title_zh", "summary_zh"],
                },
            ),
        )
        payload = json.loads(result.content)
    except (LLMConfigurationError, json.JSONDecodeError, TypeError, ValueError, RuntimeError):
        return fallback
    title_zh = str(payload.get("title_zh") or "").strip()
    summary_zh = str(payload.get("summary_zh") or "").strip()
    if not title_zh or not summary_zh:
        return fallback
    return TranslationResult(
        title_original=fallback.title_original,
        summary_original=fallback.summary_original,
        title_zh=title_zh[:300],
        summary_zh=summary_zh[:1200],
        source_language=fallback.source_language,
        translation_status="llm",
        translation_model=result.model,
        translation_prompt_version=TRANSLATION_PROMPT_VERSION,
        translation_glossary_version=GLOSSARY_VERSION,
        translated_at=datetime.now(timezone.utc),
    )


def apply_news_event_translation(data: dict[str, Any]) -> dict[str, Any]:
    translated = translate_market_text_pair(str(data["title"]), str(data.get("summary") or data["title"]))
    fields = translated.to_model_fields()
    for key, value in fields.items():
        if data.get(key) not in (None, "", "pending", "unknown"):
            fields[key] = data[key]
        elif key in {"title_original", "summary_original"} and data.get(key) is None:
            fields[key] = translated.title_original if key == "title_original" else translated.summary_original
    return {**data, **fields}


def apply_alert_translation(data: dict[str, Any]) -> dict[str, Any]:
    translated = translate_market_text_pair(str(data["title"]), str(data.get("summary") or data["title"]))
    fields = translated.to_model_fields()
    for key in fields:
        if data.get(key) not in (None, "", "pending", "unknown"):
            fields[key] = data[key]
    return {**data, **fields}


def detect_language(text: str) -> str:
    if not text.strip():
        return "unknown"
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    alpha_count = sum(1 for char in text if char.isalpha())
    if cjk_count >= 2 and cjk_count >= alpha_count * 0.25:
        return "zh"
    return "en"


def glossary_translate(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    for code, label in sorted(SYMBOL_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        value = re.sub(rf"\b{re.escape(code)}\b", f"{code}({label})", value)
    for source, target in sorted(TERM_PAIRS, key=lambda item: len(item[0]), reverse=True):
        value = re.sub(
            rf"\b{re.escape(source)}\b",
            target,
            value,
            flags=re.IGNORECASE,
        )
    value = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", value)
    value = re.sub(r"\s*-\s*", " - ", value)
    value = re.sub(r"\s+", " ", value)
    value = value.replace(" ,", "，").replace(", ", "，")
    value = value.replace(". ", "。")
    value = value.replace(" .", "。")
    return value.strip()


def event_type_label(value: str) -> str:
    return EVENT_TYPE_LABELS.get(value, value)


def direction_label(value: str) -> str:
    return DIRECTION_LABELS.get(value, value)


def severity_label_zh(value: str) -> str:
    return SEVERITY_LABELS.get(value, value)
