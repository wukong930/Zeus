from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_events import NewsEvent
from app.services.event_intelligence.profiles import DEFAULT_COMMODITY_PROFILES, symbols_matching_text
from app.services.llm.registry import complete_with_llm_controls
from app.services.llm.types import LLMCompletionOptions, LLMCompletionResult, LLMMessage

SemanticCompleter = Callable[..., Awaitable[LLMCompletionResult]]

SEMANTIC_PROMPT_VERSION = "event-intelligence-semantic-v1"
EVENT_INTELLIGENCE_SEMANTIC_MODULE = "event_intelligence_semantic"
ALLOWED_DIRECTIONS = {"bullish", "bearish", "mixed", "watch"}
ALLOWED_MECHANISMS = {
    "supply",
    "demand",
    "logistics",
    "policy",
    "inventory",
    "cost",
    "risk_sentiment",
    "geopolitical",
    "weather",
    "macro",
}
KNOWN_SYMBOLS = set(DEFAULT_COMMODITY_PROFILES)


class EventSemanticHypothesis(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    region_id: str | None = Field(default=None, max_length=80)
    mechanism: str
    direction: str
    confidence: float = Field(ge=0, le=1)
    horizon: str = Field(default="short", max_length=20)
    rationale: str = Field(default="", max_length=600)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    counterevidence: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = str(value).strip().upper()
        if symbol not in KNOWN_SYMBOLS:
            raise ValueError("unsupported commodity symbol")
        return symbol

    @field_validator("mechanism")
    @classmethod
    def validate_mechanism(cls, value: str) -> str:
        mechanism = str(value).strip().lower()
        if mechanism not in ALLOWED_MECHANISMS:
            raise ValueError("unsupported mechanism")
        return mechanism

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: str) -> str:
        direction = str(value).strip().lower()
        if direction not in ALLOWED_DIRECTIONS:
            raise ValueError("unsupported direction")
        return direction

    @field_validator("region_id")
    @classmethod
    def normalize_region(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("evidence", "counterevidence")
    @classmethod
    def normalize_text_items(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, max_length=600, limit=8)


class EventSemanticExtraction(BaseModel):
    event_type: str | None = Field(default=None, max_length=40)
    direction: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    entities: list[str] = Field(default_factory=list, max_length=24)
    symbols: list[str] = Field(default_factory=list, max_length=40)
    regions: list[str] = Field(default_factory=list, max_length=40)
    mechanisms: list[str] = Field(default_factory=list, max_length=10)
    evidence: list[str] = Field(default_factory=list, max_length=8)
    counterevidence: list[str] = Field(default_factory=list, max_length=8)
    requires_manual_confirmation: bool | None = None
    hypotheses: list[EventSemanticHypothesis] = Field(default_factory=list, max_length=80)
    model: str = "unknown"
    prompt_version: str = SEMANTIC_PROMPT_VERSION

    @field_validator("direction")
    @classmethod
    def normalize_direction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        direction = str(value).strip().lower()
        return direction if direction in ALLOWED_DIRECTIONS else None

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        symbols = _normalize_text_list(values, max_length=20, limit=40, uppercase=True)
        return [symbol for symbol in symbols if symbol in KNOWN_SYMBOLS]

    @field_validator("regions")
    @classmethod
    def normalize_regions(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, max_length=80, limit=40)

    @field_validator("mechanisms")
    @classmethod
    def normalize_mechanisms(cls, values: list[str]) -> list[str]:
        mechanisms: list[str] = []
        for value in values:
            mechanism = str(value).strip().lower()
            if mechanism in ALLOWED_MECHANISMS:
                mechanisms.append(mechanism)
        return list(dict.fromkeys(mechanisms))[:10]

    @field_validator("entities")
    @classmethod
    def normalize_entities(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, max_length=120, limit=24)

    @field_validator("evidence", "counterevidence")
    @classmethod
    def normalize_evidence(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, max_length=600, limit=8)


SEMANTIC_JSON_SCHEMA: dict[str, Any] = EventSemanticExtraction.model_json_schema()

SEMANTIC_SYSTEM_PROMPT = """You are Zeus Event Intelligence Engine.
Extract commodity-impact hypotheses from one event. Return JSON only.
Rules:
- Use the provided commodity universe; do not invent futures symbols.
- A single event can affect different commodities through different mechanisms and directions.
- Prefer "watch" when the causal direction is unclear or needs confirmation.
- Include counterevidence and manual review flags for rumors, single-source claims, or weak evidence.
- Keep rationales concise and grounded in the event text.
"""


async def extract_news_event_semantics(
    session: AsyncSession,
    news_event: NewsEvent,
    *,
    completer: SemanticCompleter = complete_with_llm_controls,
) -> EventSemanticExtraction:
    result = await completer(
        module=EVENT_INTELLIGENCE_SEMANTIC_MODULE,
        options=LLMCompletionOptions(
            messages=[
                LLMMessage(role="system", content=SEMANTIC_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=json.dumps(
                        build_semantic_extraction_payload(news_event),
                        ensure_ascii=False,
                    ),
                ),
            ],
            temperature=0.1,
            max_tokens=1400,
            json_mode=True,
            json_schema=SEMANTIC_JSON_SCHEMA,
        ),
        session=session,
    )
    return parse_semantic_extraction(result.content, model=result.model)


def parse_semantic_extraction(content: str, *, model: str = "unknown") -> EventSemanticExtraction:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Semantic extraction response is not valid JSON") from exc

    if isinstance(data, dict) and isinstance(data.get("extraction"), dict):
        data = data["extraction"]
    if not isinstance(data, dict):
        raise ValueError("Semantic extraction response must be a JSON object")

    raw_hypotheses = data.pop("hypotheses", [])
    hypotheses: list[EventSemanticHypothesis] = []
    if isinstance(raw_hypotheses, list):
        for raw_item in raw_hypotheses:
            try:
                hypotheses.append(EventSemanticHypothesis.model_validate(raw_item))
            except ValidationError:
                continue
    data["hypotheses"] = hypotheses
    data["model"] = model
    data.setdefault("prompt_version", SEMANTIC_PROMPT_VERSION)
    try:
        return EventSemanticExtraction.model_validate(data)
    except ValidationError as exc:
        raise ValueError("Semantic extraction response failed validation") from exc


def build_semantic_extraction_payload(news_event: NewsEvent) -> dict[str, Any]:
    text = _combined_news_text(news_event)
    candidate_symbols = _candidate_symbols(news_event, text)
    return {
        "prompt_version": SEMANTIC_PROMPT_VERSION,
        "event": {
            "id": str(news_event.id),
            "source": news_event.source,
            "title": news_event.title,
            "summary": news_event.summary,
            "content_text": news_event.content_text,
            "event_type": news_event.event_type,
            "affected_symbols": news_event.affected_symbols,
            "direction": news_event.direction,
            "severity": news_event.severity,
            "time_horizon": news_event.time_horizon,
            "llm_confidence": news_event.llm_confidence,
            "source_count": news_event.source_count,
            "verification_status": news_event.verification_status,
            "requires_manual_confirmation": news_event.requires_manual_confirmation,
            "extraction_payload": news_event.extraction_payload,
        },
        "candidate_symbols": candidate_symbols,
        "allowed_mechanisms": sorted(ALLOWED_MECHANISMS),
        "allowed_directions": sorted(ALLOWED_DIRECTIONS),
        "commodity_universe": [
            {
                "symbol": profile.symbol,
                "name_zh": profile.name_zh,
                "sector": profile.sector,
                "regions": list(profile.regions),
                "top_mechanisms": [
                    mechanism
                    for mechanism, _weight in sorted(
                        profile.mechanism_weights.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:5]
                ],
                "keywords": list(profile.keywords),
            }
            for profile in DEFAULT_COMMODITY_PROFILES.values()
        ],
        "output_contract": {
            "symbols": "Only exchange symbols from commodity_universe.",
            "hypotheses": (
                "Each item must contain symbol, region_id, mechanism, direction, confidence, "
                "horizon, rationale, evidence, counterevidence."
            ),
        },
    }


def _candidate_symbols(news_event: NewsEvent, text: str) -> list[str]:
    symbols = [
        str(symbol).strip().upper()
        for symbol in news_event.affected_symbols
        if str(symbol).strip()
    ]
    symbols.extend(symbols_matching_text(text))
    return list(dict.fromkeys(symbols))


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


def _normalize_text_list(
    values: list[str],
    *,
    max_length: int,
    limit: int,
    uppercase: bool = False,
) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if uppercase:
            text = text.upper()
        normalized.append(text[:max_length])
    return list(dict.fromkeys(normalized))[:limit]
