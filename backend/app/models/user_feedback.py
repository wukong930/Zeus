from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserFeedback(Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        Index("ix_user_feedback_alert_id", "alert_id"),
        Index("ix_user_feedback_recommendation_id", "recommendation_id"),
        Index("ix_user_feedback_signal_type", "signal_type"),
        Index("ix_user_feedback_recorded_at", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    recommendation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signal_type: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(40))
    agree: Mapped[str] = mapped_column(String(20), nullable=False)
    disagreement_reason: Mapped[str | None] = mapped_column(Text)
    will_trade: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
