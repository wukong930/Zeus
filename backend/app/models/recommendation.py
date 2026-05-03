from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_status", "status"),
        Index("ix_recommendations_strategy_id", "strategy_id"),
        Index("ix_recommendations_alert_id", "alert_id"),
        Index("ix_recommendations_created_at", "created_at"),
        Index("ix_recommendations_actual_exit_reason", "actual_exit_reason"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="set null"),
    )
    alert_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="set null"),
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(20), nullable=False)
    legs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    margin_efficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    margin_required: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    one_liner: Mapped[str | None] = mapped_column(Text)
    risk_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deferred_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ignored_reason: Mapped[str | None] = mapped_column(Text)
    execution_feedback_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    max_holding_days: Mapped[int | None] = mapped_column(Integer)
    position_size_pct: Mapped[float | None] = mapped_column(Float)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Float)
    backtest_summary: Mapped[dict | None] = mapped_column(JSONB)
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    take_profit: Mapped[float | None] = mapped_column(Float)
    actual_entry: Mapped[float | None] = mapped_column(Float)
    actual_exit: Mapped[float | None] = mapped_column(Float)
    actual_exit_reason: Mapped[str | None] = mapped_column(String(40))
    pnl_realized: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    mfe: Mapped[float | None] = mapped_column(Float)
    holding_period_days: Mapped[float | None] = mapped_column(Float)
