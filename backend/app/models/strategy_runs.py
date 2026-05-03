from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrategyRun(Base):
    __tablename__ = "strategy_runs"
    __table_args__ = (
        Index("ix_strategy_runs_hash", "strategy_hash"),
        Index("ix_strategy_runs_space", "strategy_space"),
        Index("ix_strategy_runs_run_at", "run_at"),
        Index("ix_strategy_runs_calibration_strategy", "calibration_strategy"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    strategy_name: Mapped[str | None] = mapped_column(Text)
    strategy_space: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    deflated_sharpe: Mapped[float] = mapped_column(Float, nullable=False)
    deflated_pvalue: Mapped[float] = mapped_column(Float, nullable=False)
    fdr_method: Mapped[str | None] = mapped_column(String(30))
    fdr_threshold: Mapped[float | None] = mapped_column(Float)
    passed_gate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calibration_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="pit")
    result_warning: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_by: Mapped[str | None] = mapped_column(String(80))
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
