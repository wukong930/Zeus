from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EventIntelligenceItem(Base):
    __tablename__ = "event_intelligence_items"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_event_intelligence_items_source",
        ),
        Index("ix_event_intelligence_items_event_type", "event_type"),
        Index("ix_event_intelligence_items_status", "status"),
        Index("ix_event_intelligence_items_event_timestamp", "event_timestamp"),
        Index("ix_event_intelligence_items_symbols", "symbols", postgresql_using="gin"),
        Index("ix_event_intelligence_items_regions", "regions", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    regions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mechanisms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    counterevidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="shadow_review", nullable=False)
    requires_manual_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_reliability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    source_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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

    impact_links: Mapped[list["EventImpactLink"]] = relationship(
        back_populates="event_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[list["EventIntelligenceAuditLog"]] = relationship(
        back_populates="event_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class EventImpactLink(Base):
    __tablename__ = "event_impact_links"
    __table_args__ = (
        UniqueConstraint(
            "event_item_id",
            "symbol",
            "region_id",
            "mechanism",
            name="uq_event_impact_links_scope",
        ),
        Index("ix_event_impact_links_symbol", "symbol"),
        Index("ix_event_impact_links_region_id", "region_id"),
        Index("ix_event_impact_links_mechanism", "mechanism"),
        Index("ix_event_impact_links_direction", "direction"),
        Index("ix_event_impact_links_status", "status"),
        Index("ix_event_impact_links_confidence", "confidence"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_intelligence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    region_id: Mapped[str | None] = mapped_column(String(80))
    mechanism: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    horizon: Mapped[str] = mapped_column(String(20), default="short", nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    counterevidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), default="shadow_review", nullable=False)
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

    event_item: Mapped[EventIntelligenceItem] = relationship(back_populates="impact_links")


class EventIntelligenceAuditLog(Base):
    __tablename__ = "event_intelligence_audit_logs"
    __table_args__ = (
        Index("ix_event_intelligence_audit_logs_event_item_id", "event_item_id"),
        Index("ix_event_intelligence_audit_logs_action", "action"),
        Index("ix_event_intelligence_audit_logs_actor", "actor"),
        Index("ix_event_intelligence_audit_logs_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_intelligence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(80))
    before_status: Mapped[str | None] = mapped_column(String(30))
    after_status: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event_item: Mapped[EventIntelligenceItem] = relationship(back_populates="audit_logs")
