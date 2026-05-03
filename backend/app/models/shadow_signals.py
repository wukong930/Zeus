from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShadowSignal(Base):
    __tablename__ = "shadow_signals"
    __table_args__ = (
        Index("ix_shadow_signals_run", "shadow_run_id"),
        Index("ix_shadow_signals_event", "source_event_type", "source_event_id"),
        Index("ix_shadow_signals_lookup", "signal_type", "category", "symbol"),
        Index("ix_shadow_signals_would_emit", "would_emit"),
        Index("ix_shadow_signals_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    shadow_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[str | None] = mapped_column(String(120))
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(40))
    would_emit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    production_signal_track_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    production_alert_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    signal_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    context_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    score_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
