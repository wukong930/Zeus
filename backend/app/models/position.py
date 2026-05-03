from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_status", "status"),
        Index("ix_positions_strategy_id", "strategy_id"),
        Index("ix_positions_recommendation_id", "recommendation_id"),
        Index("ix_positions_opened_at", "opened_at"),
        Index("ix_positions_monitoring_priority", "monitoring_priority"),
        Index("ix_positions_data_mode", "data_mode"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="set null"),
    )
    strategy_name: Mapped[str | None] = mapped_column(Text)
    recommendation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="set null"),
    )
    legs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_spread: Mapped[float] = mapped_column(Float, nullable=False)
    current_spread: Mapped[float] = mapped_column(Float, nullable=False)
    spread_unit: Mapped[str] = mapped_column(Text, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    total_margin_used: Mapped[float] = mapped_column(Float, nullable=False)
    exit_condition: Mapped[str] = mapped_column(Text, nullable=False)
    target_z_score: Mapped[float] = mapped_column(Float, nullable=False)
    current_z_score: Mapped[float] = mapped_column(Float, nullable=False)
    half_life_days: Mapped[float] = mapped_column(Float, nullable=False)
    days_held: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    manual_entry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avg_entry_price: Mapped[float | None] = mapped_column(Float)
    monitoring_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    propagation_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_mode: Mapped[str] = mapped_column(String(30), default="position_aware", nullable=False)
