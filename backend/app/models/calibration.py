from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SignalCalibration(Base):
    __tablename__ = "signal_calibration"
    __table_args__ = (
        Index("ix_signal_calibration_lookup", "signal_type", "category", "regime"),
        Index("ix_signal_calibration_effective", "effective_from", "effective_to"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    regime: Mapped[str] = mapped_column(String(40), nullable=False)
    base_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    effective_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    rolling_hit_rate: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    miss_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alpha_prior: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    beta_prior: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    decay_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
