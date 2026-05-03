from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SlippageModel(Base):
    __tablename__ = "slippage_models"
    __table_args__ = (
        Index("ix_slippage_models_symbol_tier", "symbol", "contract_tier"),
        Index("ix_slippage_models_effective", "effective_from", "effective_to"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    contract_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    base_slippage_bps: Mapped[float] = mapped_column(Float, nullable=False)
    vol_multiplier: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    liquidity_multiplier: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tod_multiplier: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    delivery_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    limit_locked_fillable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
