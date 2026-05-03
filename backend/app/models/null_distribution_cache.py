from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NullDistributionCache(Base):
    __tablename__ = "null_distribution_cache"
    __table_args__ = (
        UniqueConstraint(
            "signal_type",
            "category",
            "computed_for",
            name="uq_null_distribution_signal_category_date",
        ),
        Index("ix_null_distribution_lookup", "signal_type", "category", "computed_for"),
        Index("ix_null_distribution_computed_at", "computed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_for: Mapped[date] = mapped_column(Date, nullable=False)
    statistic_name: Mapped[str] = mapped_column(String(40), default="signal_strength", nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pvalue_threshold: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    distribution_stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
