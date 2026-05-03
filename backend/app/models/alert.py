from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
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
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
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
