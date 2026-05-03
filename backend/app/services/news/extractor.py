import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.news.dedup import news_dedup_hash
from app.services.news.types import RawNewsItem

EVENT_TYPES = {"policy", "supply", "demand", "inventory", "geopolitical", "weather", "breaking"}
DIRECTIONS = {"bullish", "bearish", "mixed", "unclear"}
TIME_HORIZONS = {"immediate", "short", "medium", "long"}

SYMBOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "RB": ("螺纹", "建材", "钢材", "rebar"),
    "HC": ("热卷", "hot rolled", "coil"),
    "I": ("铁矿", "iron ore"),
    "J": ("焦炭", "coke"),
    "JM": ("焦煤", "coking coal"),
    "RU": ("天然橡胶", "橡胶", "rubber", "latex", "胶水", "割胶"),
    "NR": ("20号胶", "nr", "natural rubber", "cup lump"),
    "SC": ("原油", "crude", "oil", "opec"),
    "CU": ("铜", "copper"),
    "AL": ("铝", "aluminum", "aluminium"),
    "ZN": ("锌", "zinc"),
    "NI": ("镍", "nickel"),
    "P": ("棕榈油", "palm oil"),
    "M": ("豆粕", "soymeal"),
    "Y": ("豆油", "soybean oil"),
}

BULLISH_MARKERS = (
    "减产",
    "停产",
    "限产",
    "供应下降",
    "出口限制",
    "库存下降",
    "暴雨",
    "洪水",
    "干旱",
    "台风",
    "罢工",
    "停割",
    "割胶受阻",
    "cut",
    "outage",
    "strike",
    "export ban",
    "flood",
    "drought",
    "heavy rain",
    "tapping disruption",
)
BEARISH_MARKERS = (
    "增产",
    "复产",
    "供应增加",
    "库存增加",
    "需求下降",
    "进口增加",
    "开割恢复",
    "下调",
    "surplus",
    "inventory build",
    "demand weak",
    "tapping resumes",
)


class StructuredNewsEvent(BaseModel):
    source: str
    raw_url: str | None = None
    title: str
    summary: str
    content_text: str | None = None
    published_at: datetime
    event_type: str = Field(pattern="^(policy|supply|demand|inventory|geopolitical|weather|breaking)$")
    affected_symbols: list[str] = Field(default_factory=list)
    direction: str = Field(pattern="^(bullish|bearish|mixed|unclear)$")
    severity: int = Field(ge=1, le=5)
    time_horizon: str = Field(pattern="^(immediate|short|medium|long)$")
    llm_confidence: float = Field(ge=0, le=1)
    source_count: int = Field(default=1, ge=1)
    verification_status: str | None = None
    dedup_hash: str | None = None
    extraction_payload: dict = Field(default_factory=dict)

    @field_validator("affected_symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return sorted({symbol.strip().upper() for symbol in value if symbol.strip()})

    def with_dedup_hash(self) -> "StructuredNewsEvent":
        if self.dedup_hash is not None:
            return self
        return self.model_copy(
            update={
                "dedup_hash": news_dedup_hash(
                    title=self.title,
                    published_at=self.published_at,
                    affected_symbols=self.affected_symbols,
                )
            }
        )


async def extract_news_event(item: RawNewsItem) -> StructuredNewsEvent:
    return extract_news_event_sync(item)


def extract_news_event_sync(item: RawNewsItem) -> StructuredNewsEvent:
    text = " ".join(part for part in (item.title, item.content_text or "") if part)
    event_type = infer_event_type(text)
    direction = infer_direction(text)
    severity = infer_severity(text, event_type)
    time_horizon = infer_time_horizon(text, event_type)
    metadata = dict(item.metadata or {})
    affected_symbols = sorted(
        set(infer_symbols(text))
        | {
            str(symbol).strip().upper()
            for symbol in metadata.get("affected_symbols", [])
            if str(symbol).strip()
        }
    )
    summary = summarize(item.title, item.content_text)
    event = StructuredNewsEvent(
        source=item.source,
        raw_url=item.raw_url,
        title=item.title,
        summary=summary,
        content_text=item.content_text,
        published_at=item.published_at,
        event_type=event_type,
        affected_symbols=affected_symbols,
        direction=direction,
        severity=severity,
        time_horizon=time_horizon,
        llm_confidence=float(metadata.get("llm_confidence") or 0.62),
        source_count=max(1, int(metadata.get("source_count") or 1)),
        verification_status=metadata.get("verification_status"),
        extraction_payload={
            "extractor": "deterministic_fallback",
            "collector_metadata": metadata,
        },
    )
    return event.with_dedup_hash()


def infer_event_type(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("政策", "发改委", "交易所", "关税", "policy", "tariff")):
        return "policy"
    if any(
        marker in lowered
        for marker in (
            "暴雨",
            "台风",
            "天气",
            "降雨",
            "洪水",
            "干旱",
            "weather",
            "rain",
            "rainfall",
            "storm",
            "flood",
            "drought",
            "monsoon",
        )
    ):
        return "weather"
    if any(marker in lowered for marker in ("库存", "inventory", "stockpile")):
        return "inventory"
    if any(marker in lowered for marker in ("需求", "消费", "采购", "demand")):
        return "demand"
    if any(
        marker in lowered
        for marker in (
            "减产",
            "停产",
            "矿山",
            "供应",
            "停割",
            "割胶",
            "开割",
            "出口",
            "supply",
            "opec",
            "tapping",
            "export",
        )
    ):
        return "supply"
    if any(marker in lowered for marker in ("地缘", "制裁", "war", "sanction")):
        return "geopolitical"
    return "breaking"


def infer_direction(text: str) -> str:
    lowered = text.lower()
    bullish = any(marker in lowered for marker in BULLISH_MARKERS)
    bearish = any(marker in lowered for marker in BEARISH_MARKERS)
    if bullish and bearish:
        return "mixed"
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "unclear"


def infer_severity(text: str, event_type: str) -> int:
    lowered = text.lower()
    if any(marker in lowered for marker in ("opec", "发改委", "交易所", "出口禁令", "sanction")):
        return 5
    if any(marker in lowered for marker in ("rubber", "天然橡胶", "割胶")) and event_type in {
        "weather",
        "supply",
        "policy",
    }:
        return 4
    if event_type in {"policy", "supply", "weather", "geopolitical"}:
        return 4
    if event_type in {"inventory", "demand"}:
        return 3
    return 2


def infer_time_horizon(text: str, event_type: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("突发", "快讯", "immediate", "breaking")):
        return "immediate"
    if event_type in {"weather", "inventory"}:
        return "short"
    if event_type in {"policy", "supply"}:
        return "medium"
    return "short"


def infer_symbols(text: str) -> list[str]:
    lowered = text.lower()
    symbols = {
        symbol
        for symbol, keywords in SYMBOL_KEYWORDS.items()
        if any(keyword.lower() in lowered for keyword in keywords)
    }
    explicit_codes = re.findall(r"\b[A-Z]{1,3}\d{3,4}\b|\b[A-Z]{1,3}\b", text)
    for code in explicit_codes:
        root = re.sub(r"\d+", "", code.upper())
        if root in SYMBOL_KEYWORDS:
            symbols.add(root)
    return sorted(symbols)


def summarize(title: str, content_text: str | None) -> str:
    if not content_text:
        return title
    compact = re.sub(r"\s+", " ", content_text).strip()
    if len(compact) <= 180:
        return compact
    return compact[:177].rstrip() + "..."
