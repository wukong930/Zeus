from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    MAX_GOVERNANCE_TEXT_LENGTH,
    MAX_INGEST_SYMBOL_LENGTH,
    MAX_NEWS_SUMMARY_LENGTH,
    MAX_NEWS_TITLE_LENGTH,
    ORMModel,
    StrictInputModel,
    validate_governance_json_object,
)

EVENT_INTELLIGENCE_SOURCE_PATTERN = (
    "^(news_event|manual|weather|market|social|macro|shipping|research)$"
)
EVENT_INTELLIGENCE_STATUS_PATTERN = "^(shadow_review|human_review|confirmed|rejected)$"
EVENT_IMPACT_DIRECTION_PATTERN = "^(bullish|bearish|mixed|watch)$"
EVENT_IMPACT_MECHANISM_PATTERN = (
    "^(supply|demand|logistics|policy|inventory|cost|risk_sentiment|"
    "geopolitical|weather|macro)$"
)

MAX_EVENT_INTELLIGENCE_LIST_ITEMS = 40
MAX_EVENT_INTELLIGENCE_ENTITY_LENGTH = 120
MAX_EVENT_INTELLIGENCE_REGION_LENGTH = 80


class EventIntelligenceCreate(StrictInputModel):
    source_type: str = Field(pattern=EVENT_INTELLIGENCE_SOURCE_PATTERN)
    source_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=MAX_NEWS_TITLE_LENGTH)
    summary: str = Field(min_length=1, max_length=MAX_NEWS_SUMMARY_LENGTH)
    event_type: str = Field(min_length=1, max_length=40)
    event_timestamp: datetime
    entities: list[str] = Field(default_factory=list, max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS)
    symbols: list[str] = Field(default_factory=list, max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS)
    regions: list[str] = Field(default_factory=list, max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS)
    mechanisms: list[str] = Field(default_factory=list, max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS)
    evidence: list[str] = Field(default_factory=list, max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS)
    counterevidence: list[str] = Field(
        default_factory=list,
        max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS,
    )
    confidence: float = Field(default=0, ge=0, le=1)
    impact_score: float = Field(default=0, ge=0, le=100)
    status: str = Field(default="shadow_review", pattern=EVENT_INTELLIGENCE_STATUS_PATTERN)
    requires_manual_confirmation: bool = False
    source_reliability: float = Field(default=0.5, ge=0, le=1)
    freshness_score: float = Field(default=1, ge=0, le=1)
    source_payload: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value, max_length=MAX_INGEST_SYMBOL_LENGTH, uppercase=True)

    @field_validator("entities")
    @classmethod
    def normalize_entities(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value, max_length=MAX_EVENT_INTELLIGENCE_ENTITY_LENGTH)

    @field_validator("regions", "mechanisms")
    @classmethod
    def normalize_short_labels(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value, max_length=MAX_EVENT_INTELLIGENCE_REGION_LENGTH)

    @field_validator("evidence", "counterevidence")
    @classmethod
    def validate_evidence_text(cls, value: list[str]) -> list[str]:
        for item in value:
            if len(item) > MAX_GOVERNANCE_TEXT_LENGTH:
                raise ValueError(
                    f"evidence entries can be at most {MAX_GOVERNANCE_TEXT_LENGTH} characters"
                )
        return _normalize_text_list(value, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("source_payload")
    @classmethod
    def validate_source_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="source_payload")


class EventIntelligenceRead(EventIntelligenceCreate, ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class EventImpactLinkRead(ORMModel):
    id: UUID
    event_item_id: UUID
    symbol: str
    region_id: str | None = None
    mechanism: str
    direction: str
    confidence: float
    impact_score: float
    horizon: str
    rationale: str
    evidence: list[str]
    counterevidence: list[str]
    status: str
    created_at: datetime
    updated_at: datetime


class EventImpactLinkUpdate(StrictInputModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=MAX_INGEST_SYMBOL_LENGTH)
    region_id: str | None = Field(default=None, max_length=MAX_EVENT_INTELLIGENCE_REGION_LENGTH)
    mechanism: str | None = Field(default=None, pattern=EVENT_IMPACT_MECHANISM_PATTERN)
    direction: str | None = Field(default=None, pattern=EVENT_IMPACT_DIRECTION_PATTERN)
    confidence: float | None = Field(default=None, ge=0, le=1)
    impact_score: float | None = Field(default=None, ge=0, le=100)
    horizon: str | None = Field(default=None, min_length=1, max_length=20)
    rationale: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)
    evidence: list[str] | None = Field(
        default=None,
        max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS,
    )
    counterevidence: list[str] | None = Field(
        default=None,
        max_length=MAX_EVENT_INTELLIGENCE_LIST_ITEMS,
    )
    edited_by: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @field_validator("region_id", "mechanism", "direction", "horizon", "rationale", "note")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("evidence", "counterevidence")
    @classmethod
    def validate_optional_evidence(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for item in value:
            if len(item) > MAX_GOVERNANCE_TEXT_LENGTH:
                raise ValueError(
                    f"evidence entries can be at most {MAX_GOVERNANCE_TEXT_LENGTH} characters"
                )
        return _normalize_text_list(value, max_length=MAX_GOVERNANCE_TEXT_LENGTH)


class EventIntelligenceResolveResponse(BaseModel):
    event: EventIntelligenceRead
    impact_links: list[EventImpactLinkRead]
    created: bool


class EventIntelligenceAuditLogRead(ORMModel):
    id: UUID
    event_item_id: UUID
    action: str
    actor: str | None = None
    before_status: str | None = None
    after_status: str | None = None
    note: str | None = None
    payload: dict[str, Any]
    created_at: datetime


class EventIntelligenceDecisionCreate(StrictInputModel):
    decision: str = Field(pattern="^(confirm|reject|request_review|shadow_review)$")
    decided_by: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)
    confidence_override: float | None = Field(default=None, ge=0, le=1)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        max_length=MAX_GOVERNANCE_JSON_TOP_LEVEL_KEYS,
    )

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="payload")


class EventIntelligenceDecisionResponse(BaseModel):
    event: EventIntelligenceRead
    audit_log: EventIntelligenceAuditLogRead


class EventImpactLinkUpdateResponse(BaseModel):
    event: EventIntelligenceRead
    impact_link: EventImpactLinkRead
    audit_log: EventIntelligenceAuditLogRead


class EventIntelligenceEvalCaseRead(BaseModel):
    id: str
    title: str
    source_text: str
    expected_symbols: list[str]
    expected_mechanisms: list[str]
    expected_directions: list[str]
    review_note: str


class EventIntelligenceQualityIssue(BaseModel):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str


class EventImpactLinkQualityRead(BaseModel):
    id: UUID
    symbol: str
    mechanism: str
    score: int = Field(ge=0, le=100)
    status: Literal["blocked", "review", "passed"]
    passed_gate: bool
    issues: list[EventIntelligenceQualityIssue] = Field(default_factory=list)


class EventIntelligenceQualityRead(BaseModel):
    event_id: UUID
    score: int = Field(ge=0, le=100)
    status: Literal["blocked", "review", "shadow_ready", "decision_grade"]
    passed_gate: bool
    decision_grade: bool
    issues: list[EventIntelligenceQualityIssue] = Field(default_factory=list)
    link_reports: list[EventImpactLinkQualityRead] = Field(default_factory=list)


class EventIntelligenceQualitySummary(BaseModel):
    generated_at: datetime
    total: int
    average_score: int = Field(ge=0, le=100)
    blocked: int
    review: int
    shadow_ready: int
    decision_grade: int
    reports: list[EventIntelligenceQualityRead]


def _normalize_text_list(
    values: list[str],
    *,
    max_length: int,
    uppercase: bool = False,
) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if uppercase:
            text = text.upper()
        if len(text) > max_length:
            raise ValueError(f"list entries can be at most {max_length} characters")
        normalized.append(text)
    return list(dict.fromkeys(normalized))
