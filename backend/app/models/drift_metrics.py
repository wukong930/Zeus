from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DriftMetric(Base):
    __tablename__ = "drift_metrics"
    __table_args__ = (
        Index("ix_drift_metrics_type", "metric_type"),
        Index("ix_drift_metrics_category", "category"),
        Index("ix_drift_metrics_severity", "drift_severity"),
        Index("ix_drift_metrics_computed_at", "computed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str | None] = mapped_column(String(20))
    feature_name: Mapped[str | None] = mapped_column(String(40))
    current_value: Mapped[float | None] = mapped_column(Float)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    psi: Mapped[float | None] = mapped_column(Float)
    drift_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
