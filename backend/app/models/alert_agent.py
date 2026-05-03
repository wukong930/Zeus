from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AlertDedupCache(Base):
    __tablename__ = "alert_dedup_cache"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "direction",
            "evaluator",
            name="uq_alert_dedup_symbol_direction_evaluator",
        ),
        Index("ix_alert_dedup_lookup", "symbol", "direction", "evaluator"),
        Index("ix_alert_dedup_signal_hash", "signal_combination_hash"),
        Index("ix_alert_dedup_last_emitted_at", "last_emitted_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluator: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_combination_hash: Mapped[str | None] = mapped_column(String(64))
    last_emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    last_score: Mapped[int | None] = mapped_column(Integer)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AlertAgentConfig(Base):
    __tablename__ = "alert_agent_config"
    __table_args__ = (
        UniqueConstraint("key", name="uq_alert_agent_config_key"),
        Index("ix_alert_agent_config_key", "key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class HumanDecision(Base):
    __tablename__ = "human_decisions"
    __table_args__ = (
        Index("ix_human_decisions_alert_id", "alert_id"),
        Index("ix_human_decisions_decision", "decision"),
        Index("ix_human_decisions_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signal_track_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_override: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
