from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import (
    MAX_GOVERNANCE_TEXT_LENGTH,
    ORMModel,
    StrictInputModel,
    validate_governance_json_object,
)

GOVERNANCE_REVIEW_STATUS_PATTERN = "^(pending|approved|rejected|reviewed|shadow_review)$"
GOVERNANCE_REVIEW_DECISION_PATTERN = "^(approve|reject|mark_reviewed|shadow_review)$"


class ChangeReviewRead(ORMModel):
    id: UUID
    source: str
    target_table: str
    target_key: str
    proposed_change: dict[str, Any]
    status: str
    reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ChangeReviewDecisionCreate(StrictInputModel):
    decision: str = Field(pattern=GOVERNANCE_REVIEW_DECISION_PATTERN)
    reviewed_by: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("reviewed_by", "note")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChangeReviewCreate(StrictInputModel):
    source: str = Field(min_length=1, max_length=40)
    target_table: str = Field(min_length=1, max_length=80)
    target_key: str = Field(min_length=1, max_length=160)
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=MAX_GOVERNANCE_TEXT_LENGTH)

    @field_validator("proposed_change")
    @classmethod
    def validate_proposed_change(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_governance_json_object(value, field_name="proposed_change")
