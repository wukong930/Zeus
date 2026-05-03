from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommodityConfig(Base):
    __tablename__ = "commodity_config"
    __table_args__ = (
        UniqueConstraint("symbol", name="uq_commodity_config_symbol"),
        Index("ix_commodity_config_sector", "sector"),
        Index("ix_commodity_config_enabled", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(String(30), nullable=False)
    cost_formula: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cost_chain: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
