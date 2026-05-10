from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.news_events import NewsEvent
from app.services.event_intelligence.profiles import profile_for_symbol, symbols_matching_text


@dataclass(frozen=True)
class EventIntelligenceDraft:
    source_type: str
    source_id: str | None
    title: str
    summary: str
    event_type: str
    event_timestamp: datetime
    entities: tuple[str, ...]
    symbols: tuple[str, ...]
    regions: tuple[str, ...]
    mechanisms: tuple[str, ...]
    evidence: tuple[str, ...]
    counterevidence: tuple[str, ...]
    confidence: float
    impact_score: float
    status: str
    requires_manual_confirmation: bool
    source_reliability: float
    freshness_score: float
    source_payload: dict


@dataclass(frozen=True)
class EventImpactLinkDraft:
    symbol: str
    region_id: str | None
    mechanism: str
    direction: str
    confidence: float
    impact_score: float
    horizon: str
    rationale: str
    evidence: tuple[str, ...]
    counterevidence: tuple[str, ...]
    status: str


MECHANISM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "weather": (
        "rain",
        "flood",
        "drought",
        "typhoon",
        "weather",
        "temperature",
        "el nino",
        "la nina",
        "降水",
        "洪涝",
        "干旱",
        "台风",
        "高温",
        "低温",
        "厄尔尼诺",
        "拉尼娜",
    ),
    "logistics": (
        "shipping",
        "freight",
        "port",
        "canal",
        "vessel",
        "carrier",
        "transport",
        "航运",
        "港口",
        "运费",
        "运输",
        "运河",
        "船舶",
        "航母",
    ),
    "geopolitical": (
        "war",
        "conflict",
        "sanction",
        "iran",
        "red sea",
        "strait",
        "opec",
        "冲突",
        "战争",
        "制裁",
        "伊朗",
        "红海",
        "海峡",
        "地缘",
        "欧佩克",
    ),
    "policy": (
        "policy",
        "tariff",
        "export ban",
        "quota",
        "subsidy",
        "regulation",
        "政策",
        "关税",
        "禁令",
        "配额",
        "补贴",
        "监管",
    ),
    "inventory": ("inventory", "stock", "warehouse", "库存", "仓单", "库容", "去库", "累库"),
    "demand": ("demand", "consumption", "purchase", "消费", "需求", "采购", "订单", "成交"),
    "supply": (
        "supply",
        "output",
        "production",
        "mine",
        "crop",
        "harvest",
        "供应",
        "产量",
        "生产",
        "矿山",
        "收割",
        "割胶",
        "开工",
    ),
    "cost": ("cost", "power", "energy", "coal", "feedstock", "成本", "电力", "能源", "煤炭", "原料"),
    "macro": (
        "fed",
        "dollar",
        "rate",
        "recession",
        "inflation",
        "macro",
        "美联储",
        "美元",
        "利率",
        "衰退",
        "通胀",
        "宏观",
    ),
    "risk_sentiment": (
        "risk",
        "selloff",
        "panic",
        "liquidity",
        "风险",
        "抛售",
        "恐慌",
        "流动性",
    ),
}

EVENT_TYPE_MECHANISMS: dict[str, tuple[str, ...]] = {
    "weather": ("weather", "supply"),
    "supply": ("supply", "logistics"),
    "demand": ("demand", "macro"),
    "inventory": ("inventory", "supply"),
    "geopolitical": ("geopolitical", "logistics", "supply"),
    "policy": ("policy", "supply", "demand"),
    "breaking": ("risk_sentiment",),
}

BEARISH_TERMS = (
    "demand weak",
    "slowdown",
    "recession",
    "surplus",
    "inventory build",
    "price cap",
    "需求走弱",
    "衰退",
    "过剩",
    "累库",
    "限价",
    "大跌",
)
BULLISH_TERMS = (
    "shortage",
    "disruption",
    "cut",
    "export ban",
    "drought",
    "flood",
    "strike",
    "短缺",
    "中断",
    "减产",
    "禁令",
    "干旱",
    "洪涝",
    "罢工",
    "大涨",
)


async def resolve_news_event_impacts(
    session: AsyncSession,
    news_event_id: UUID,
) -> tuple[EventIntelligenceItem, list[EventImpactLink], bool]:
    news_event = await session.get(NewsEvent, news_event_id)
    if news_event is None:
        raise ValueError("news event not found")

    existing = await session.scalar(
        select(EventIntelligenceItem).where(
            EventIntelligenceItem.source_type == "news_event",
            EventIntelligenceItem.source_id == str(news_event.id),
        )
    )
    if existing is not None:
        links = list(
            (
                await session.scalars(
                    select(EventImpactLink)
                    .where(EventImpactLink.event_item_id == existing.id)
                    .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
                )
            ).all()
        )
        return existing, links, False

    event_draft, link_drafts = build_event_intelligence_from_news(news_event)
    item = EventIntelligenceItem(
        source_type=event_draft.source_type,
        source_id=event_draft.source_id,
        title=event_draft.title,
        summary=event_draft.summary,
        event_type=event_draft.event_type,
        event_timestamp=event_draft.event_timestamp,
        entities=list(event_draft.entities),
        symbols=list(event_draft.symbols),
        regions=list(event_draft.regions),
        mechanisms=list(event_draft.mechanisms),
        evidence=list(event_draft.evidence),
        counterevidence=list(event_draft.counterevidence),
        confidence=event_draft.confidence,
        impact_score=event_draft.impact_score,
        status=event_draft.status,
        requires_manual_confirmation=event_draft.requires_manual_confirmation,
        source_reliability=event_draft.source_reliability,
        freshness_score=event_draft.freshness_score,
        source_payload=event_draft.source_payload,
    )
    session.add(item)
    await session.flush()

    links = [
        EventImpactLink(
            event_item_id=item.id,
            symbol=draft.symbol,
            region_id=draft.region_id,
            mechanism=draft.mechanism,
            direction=draft.direction,
            confidence=draft.confidence,
            impact_score=draft.impact_score,
            horizon=draft.horizon,
            rationale=draft.rationale,
            evidence=list(draft.evidence),
            counterevidence=list(draft.counterevidence),
            status=draft.status,
        )
        for draft in link_drafts
    ]
    session.add_all(links)
    await session.flush()
    return item, links, True


def build_event_intelligence_from_news(
    news_event: NewsEvent,
    *,
    now: datetime | None = None,
) -> tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]]:
    observed_at = now or datetime.now(UTC)
    text = _combined_news_text(news_event)
    symbols = _resolve_symbols(news_event, text)
    mechanisms = _resolve_mechanisms(news_event, text)
    reliability = _source_reliability(news_event)
    freshness = _freshness_score(news_event.published_at, observed_at)
    confidence = _clamp(news_event.llm_confidence * (0.7 + reliability * 0.3) * freshness)
    requires_manual_confirmation = _requires_manual_confirmation(news_event, confidence)
    status = "human_review" if requires_manual_confirmation else "shadow_review"
    entities = _extract_entities(news_event, text)
    regions = _regions_for_symbols(symbols)
    evidence = tuple(_compact_evidence([news_event.title, news_event.summary, news_event.raw_url or ""]))
    counterevidence = tuple(_counterevidence(news_event, mechanisms))
    direction = _resolve_direction(news_event.direction, text)

    link_drafts = _build_impact_links(
        symbols=symbols,
        mechanisms=mechanisms,
        direction=direction,
        horizon=news_event.time_horizon,
        confidence=confidence,
        evidence=evidence,
        counterevidence=counterevidence,
        status=status,
    )
    impact_score = max((link.impact_score for link in link_drafts), default=round(confidence * 100, 2))

    event_draft = EventIntelligenceDraft(
        source_type="news_event",
        source_id=str(news_event.id),
        title=news_event.title,
        summary=news_event.summary,
        event_type=news_event.event_type,
        event_timestamp=news_event.published_at,
        entities=tuple(entities),
        symbols=tuple(symbols),
        regions=tuple(regions),
        mechanisms=tuple(mechanisms),
        evidence=evidence,
        counterevidence=counterevidence,
        confidence=round(confidence, 4),
        impact_score=impact_score,
        status=status,
        requires_manual_confirmation=requires_manual_confirmation,
        source_reliability=round(reliability, 4),
        freshness_score=round(freshness, 4),
        source_payload={
            "news_event_id": str(news_event.id),
            "source": news_event.source,
            "source_count": news_event.source_count,
            "verification_status": news_event.verification_status,
            "severity": news_event.severity,
            "direction": news_event.direction,
        },
    )
    return event_draft, link_drafts


def _build_impact_links(
    *,
    symbols: list[str],
    mechanisms: list[str],
    direction: str,
    horizon: str,
    confidence: float,
    evidence: tuple[str, ...],
    counterevidence: tuple[str, ...],
    status: str,
) -> list[EventImpactLinkDraft]:
    links: list[EventImpactLinkDraft] = []
    for symbol in symbols:
        profile = profile_for_symbol(symbol)
        region_ids = profile.regions if profile else (None,)
        weighted_mechanisms = _weighted_mechanisms_for_symbol(symbol, mechanisms)
        for mechanism, weight in weighted_mechanisms:
            link_confidence = _clamp(confidence * weight)
            impact_score = round(link_confidence * 100, 2)
            for region_id in region_ids:
                links.append(
                    EventImpactLinkDraft(
                        symbol=symbol,
                        region_id=region_id,
                        mechanism=mechanism,
                        direction=direction,
                        confidence=round(link_confidence, 4),
                        impact_score=impact_score,
                        horizon=horizon,
                        rationale=_rationale(symbol, region_id, mechanism, direction),
                        evidence=evidence,
                        counterevidence=counterevidence,
                        status=status,
                    )
                )
    return sorted(links, key=lambda item: item.impact_score, reverse=True)[:80]


def _weighted_mechanisms_for_symbol(symbol: str, mechanisms: list[str]) -> list[tuple[str, float]]:
    profile = profile_for_symbol(symbol)
    if profile is None:
        return [(mechanism, 0.5) for mechanism in mechanisms[:3]]
    weighted = [
        (mechanism, profile.mechanism_weights.get(mechanism, 0.35))
        for mechanism in mechanisms
        if profile.mechanism_weights.get(mechanism, 0) >= 0.35
    ]
    if not weighted:
        weighted = sorted(
            profile.mechanism_weights.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:2]
    return sorted(weighted, key=lambda item: item[1], reverse=True)[:3]


def _resolve_symbols(news_event: NewsEvent, text: str) -> list[str]:
    symbols = [str(symbol).strip().upper() for symbol in news_event.affected_symbols if str(symbol).strip()]
    if not symbols:
        symbols = symbols_matching_text(text)
    return sorted(dict.fromkeys(symbols))


def _resolve_mechanisms(news_event: NewsEvent, text: str) -> list[str]:
    haystack = text.lower()
    mechanisms: list[str] = list(EVENT_TYPE_MECHANISMS.get(news_event.event_type, ()))
    for mechanism, keywords in MECHANISM_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            mechanisms.append(mechanism)
    return list(dict.fromkeys(mechanisms)) or ["risk_sentiment"]


def _resolve_direction(direction: str, text: str) -> str:
    if direction in {"bullish", "bearish", "mixed"}:
        return direction
    haystack = text.lower()
    bullish_hits = sum(1 for term in BULLISH_TERMS if term in haystack)
    bearish_hits = sum(1 for term in BEARISH_TERMS if term in haystack)
    if bullish_hits > bearish_hits:
        return "bullish"
    if bearish_hits > bullish_hits:
        return "bearish"
    return "watch"


def _source_reliability(news_event: NewsEvent) -> float:
    verification_status = (news_event.verification_status or "").lower()
    status_score = {
        "confirmed": 0.82,
        "cross_verified": 0.78,
        "multi_source": 0.72,
        "single_source": 0.45,
        "unverified": 0.35,
    }.get(verification_status, 0.5)
    source_score = min(0.2, max(0, (news_event.source_count - 1) * 0.04))
    return _clamp(status_score + source_score)


def _freshness_score(event_timestamp: datetime, now: datetime) -> float:
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age_hours = max(0, (now - event_timestamp).total_seconds() / 3600)
    if age_hours <= 24:
        return 1
    if age_hours <= 72:
        return 0.82
    if age_hours <= 168:
        return 0.62
    return 0.45


def _requires_manual_confirmation(news_event: NewsEvent, confidence: float) -> bool:
    return bool(
        news_event.requires_manual_confirmation
        or (news_event.severity >= 4 and news_event.source_count < 2)
        or confidence < 0.55
    )


def _regions_for_symbols(symbols: list[str]) -> list[str]:
    regions: list[str] = []
    for symbol in symbols:
        profile = profile_for_symbol(symbol)
        if profile is not None:
            regions.extend(profile.regions)
    return list(dict.fromkeys(regions))


def _extract_entities(news_event: NewsEvent, text: str) -> list[str]:
    payload = news_event.extraction_payload or {}
    payload_entities = payload.get("entities", [])
    entities: list[str] = []
    if isinstance(payload_entities, list):
        entities.extend(str(entity).strip() for entity in payload_entities if str(entity).strip())
    for marker in ("伊朗", "红海", "OPEC", "厄尔尼诺", "特朗普", "美联储"):
        if marker.lower() in text.lower():
            entities.append(marker)
    return list(dict.fromkeys(entities))[:24]


def _counterevidence(news_event: NewsEvent, mechanisms: list[str]) -> list[str]:
    items: list[str] = []
    if news_event.source_count < 2:
        items.append("当前仍是单源或弱多源信息，需要等待独立来源确认。")
    if news_event.direction == "unclear":
        items.append("方向尚不明确，应结合价格、库存和跨市场反应再确认。")
    if "weather" in mechanisms:
        items.append("天气异常需要和历史同期基准、未来预报路径共同验证。")
    if "geopolitical" in mechanisms:
        items.append("地缘事件容易反复，应观察实际航运、供应或制裁执行变化。")
    return items[:6]


def _compact_evidence(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        items.append(text[:600])
    return list(dict.fromkeys(items))[:8]


def _rationale(symbol: str, region_id: str | None, mechanism: str, direction: str) -> str:
    profile = profile_for_symbol(symbol)
    name = profile.name_zh if profile else symbol
    region_label = region_id or "global"
    return f"{name} 对 {mechanism} 机制敏感，当前事件在 {region_label} 形成 {direction} 方向的候选影响链。"


def _combined_news_text(news_event: NewsEvent) -> str:
    return "\n".join(
        part
        for part in (
            news_event.title,
            news_event.summary or "",
            news_event.content_text or "",
        )
        if part
    )


def _clamp(value: float, *, lower: float = 0, upper: float = 1) -> float:
    return max(lower, min(upper, value))
