from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveDivergenceMetric(Base):
    __tablename__ = "live_divergence_metrics"
    __table_args__ = (
        Index("ix_live_divergence_strategy", "strategy_hash"),
        Index("ix_live_divergence_type", "metric_type"),
        Index("ix_live_divergence_severity", "severity"),
        Index("ix_live_divergence_computed_at", "computed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    backtest_value: Mapped[float | None] = mapped_column(Float)
    live_value: Mapped[float | None] = mapped_column(Float)
    tracking_error: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
