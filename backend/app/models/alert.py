from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_category", "category"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_triggered_at", "triggered_at"),
        Index("ix_alerts_adversarial_passed", "adversarial_passed"),
        Index("ix_alerts_confidence_tier", "confidence_tier"),
        Index("ix_alerts_human_action_required", "human_action_required"),
        Index("ix_alerts_dedup_suppressed", "dedup_suppressed"),
        Index("ix_alerts_translation_status", "translation_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    title_original: Mapped[str | None] = mapped_column(Text)
    summary_original: Mapped[str | None] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text)
    summary_zh: Mapped[str | None] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(String(12), default="unknown", nullable=False)
    translation_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    translation_model: Mapped[str | None] = mapped_column(String(100))
    translation_prompt_version: Mapped[str | None] = mapped_column(String(60))
    translation_glossary_version: Mapped[str | None] = mapped_column(String(60))
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    adversarial_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    llm_involved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_tier: Mapped[str] = mapped_column(String(20), default="notify", nullable=False)
    human_action_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_action_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    related_assets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    spread_info: Mapped[dict | None] = mapped_column(JSONB)
    trigger_chain: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    manual_check_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    one_liner: Mapped[str | None] = mapped_column(Text)
    related_strategy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="set null"),
    )
    related_recommendation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    related_research_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_reports.id", ondelete="set null"),
    )
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
