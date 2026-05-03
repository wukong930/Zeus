from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResearchHypothesis(Base):
    __tablename__ = "research_hypotheses"
    __table_args__ = (
        Index("ix_research_hypotheses_status", "status"),
        Index("ix_research_hypotheses_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        Index("ix_research_reports_type", "type"),
        Index("ix_research_reports_published_at", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    hypotheses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_strategy_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_alert_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
