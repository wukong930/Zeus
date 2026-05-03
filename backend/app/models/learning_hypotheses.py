from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LearningHypothesis(Base):
    __tablename__ = "learning_hypotheses"
    __table_args__ = (
        Index("ix_learning_hypotheses_status", "status"),
        Index("ix_learning_hypotheses_evidence_strength", "evidence_strength"),
        Index("ix_learning_hypotheses_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    proposed_change: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counterevidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    evidence_strength: Mapped[str] = mapped_column(
        String(30),
        default="weak_evidence",
        nullable=False,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
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
