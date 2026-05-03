from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SignalTrack(Base):
    __tablename__ = "signal_track"
    __table_args__ = (
        Index("ix_signal_track_type", "signal_type"),
        Index("ix_signal_track_category", "category"),
        Index("ix_signal_track_outcome", "outcome"),
        Index("ix_signal_track_alert_id", "alert_id"),
        Index("ix_signal_track_combination_hash", "signal_combination_hash"),
        Index("ix_signal_track_regime_at_emission", "regime_at_emission"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float | None] = mapped_column(Float)
    regime: Mapped[str | None] = mapped_column(String(30))
    regime_at_emission: Mapped[str | None] = mapped_column(String(40))
    calibration_weight_at_emission: Mapped[float | None] = mapped_column(Float)
    signal_combination_hash: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    position_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    forward_return_1d: Mapped[float | None] = mapped_column(Float)
    forward_return_5d: Mapped[float | None] = mapped_column(Float)
    forward_return_20d: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
