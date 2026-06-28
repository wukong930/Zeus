from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ForecastRecord(Base):
    """A point-in-time, reproducible cross-sectional forecast.

    Emitted by services/prediction. ``decision_grade`` defaults to False — the
    forecast is advisory / shadow until governance review + shadow validation
    promote it, per the platform's governance principle. ``feature_hash`` pins
    the inputs so any forecast can be reproduced and audited.
    """

    __tablename__ = "forecast_records"
    __table_args__ = (
        Index("ix_forecast_records_signal", "signal"),
        Index("ix_forecast_records_as_of", "as_of"),
        Index("ix_forecast_records_signal_as_of_id", "signal", "as_of", "id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal: Mapped[str] = mapped_column(String(60), nullable=False)
    model_version: Mapped[str] = mapped_column(String(60), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    universe_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decision_grade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    # filled by shadow scoring once the holding period elapses (non-authoritative)
    realized_return: Mapped[float | None] = mapped_column(Float)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
