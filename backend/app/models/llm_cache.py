from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMCache(Base):
    __tablename__ = "llm_cache"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_llm_cache_key"),
        Index("ix_llm_cache_module", "module"),
        Index("ix_llm_cache_expires_at", "expires_at"),
        Index("ix_llm_cache_provider_model", "provider", "model"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    system_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"
    __table_args__ = (
        Index("ix_llm_usage_module_created", "module", "created_at"),
        Index("ix_llm_usage_provider_model", "provider", "model"),
        Index("ix_llm_usage_cache_hit", "cache_hit"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LLMBudget(Base):
    __tablename__ = "llm_budgets"
    __table_args__ = (
        UniqueConstraint("module", "period_start", name="uq_llm_budget_module_period"),
        Index("ix_llm_budgets_module", "module"),
        Index("ix_llm_budgets_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, nullable=False)
    current_spend_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
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
