from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        Index("ix_event_log_channel", "channel"),
        Index("ix_event_log_status", "status"),
        Index("ix_event_log_correlation_id", "correlation_id"),
        Index("ix_event_log_created_at", "created_at"),
        UniqueConstraint(
            "event_id",
            "channel",
            "status",
            name="uq_event_log_event_channel_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
