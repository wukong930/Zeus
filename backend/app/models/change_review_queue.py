from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChangeReviewQueue(Base):
    __tablename__ = "change_review_queue"
    __table_args__ = (
        Index("ix_change_review_queue_source", "source"),
        Index("ix_change_review_queue_status", "status"),
        Index("ix_change_review_queue_status_created_at", "status", "created_at"),
        Index("ix_change_review_queue_source_created_at", "source", "created_at"),
        Index(
            "ix_change_review_queue_triage_scan",
            "source",
            "target_table",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_change_review_queue_active_lookup",
            "source",
            "target_table",
            "target_key",
            "status",
            "created_at",
            "id",
        ),
        Index("ix_change_review_queue_target", "target_table", "target_key"),
        Index("ix_change_review_queue_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    target_table: Mapped[str] = mapped_column(String(80), nullable=False)
    target_key: Mapped[str] = mapped_column(String(160), nullable=False)
    proposed_change: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(80))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    @property
    def triage_attention_score(self) -> float | None:
        triage = _review_triage_payload(self.proposed_change)
        value = triage.get("attention_score")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def triage_tier(self) -> str | None:
        triage = _review_triage_payload(self.proposed_change)
        value = triage.get("tier")
        return str(value) if value else None

    @property
    def triage_requires_human_attention(self) -> bool | None:
        triage = _review_triage_payload(self.proposed_change)
        value = triage.get("requires_human_attention")
        return value if isinstance(value, bool) else None

    @property
    def triage_reasons(self) -> list[str]:
        triage = _review_triage_payload(self.proposed_change)
        reasons = triage.get("reasons")
        if not isinstance(reasons, list):
            return []
        return [str(reason) for reason in reasons if str(reason)]


def _review_triage_payload(proposed_change: dict | None) -> dict:
    if not isinstance(proposed_change, dict):
        return {}
    triage = proposed_change.get("review_triage")
    return triage if isinstance(triage, dict) else {}
