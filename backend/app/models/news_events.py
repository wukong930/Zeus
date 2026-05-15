from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NewsEvent(Base):
    __tablename__ = "news_events"
    __table_args__ = (
        Index("ix_news_events_source", "source"),
        Index("ix_news_events_published_at", "published_at"),
        Index("ix_news_events_event_type", "event_type"),
        Index("ix_news_events_direction", "direction"),
        Index("ix_news_events_severity", "severity"),
        Index("ix_news_events_dedup_hash", "dedup_hash", unique=True),
        Index("ix_news_events_affected_symbols", "affected_symbols", postgresql_using="gin"),
        Index("ix_news_events_translation_status", "translation_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_url: Mapped[str | None] = mapped_column(Text)
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
    content_text: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    affected_symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(30),
        default="single_source",
        nullable=False,
    )
    requires_manual_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
