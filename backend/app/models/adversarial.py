from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdversarialResult(Base):
    __tablename__ = "adversarial_results"
    __table_args__ = (
        Index("ix_adversarial_results_signal", "signal_type", "category", "regime"),
        Index("ix_adversarial_results_combination_hash", "signal_combination_hash"),
        Index("ix_adversarial_results_passed", "passed"),
        Index("ix_adversarial_results_computed_at", "computed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    regime: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_combination_hash: Mapped[str | None] = mapped_column(String(64))
    signal_track_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[str | None] = mapped_column(String(80))
    null_hypothesis_pvalue: Mapped[float | None] = mapped_column(Float)
    null_hypothesis_passed: Mapped[bool | None] = mapped_column(Boolean)
    historical_combo_hit_rate: Mapped[float | None] = mapped_column(Float)
    historical_combo_sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_combo_mode: Mapped[str] = mapped_column(
        String(20),
        default="informational",
        nullable=False,
    )
    historical_combo_passed: Mapped[bool | None] = mapped_column(Boolean)
    structural_counter_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    structural_counter_passed: Mapped[bool | None] = mapped_column(Boolean)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
