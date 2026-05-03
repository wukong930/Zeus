from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CostSnapshot(Base):
    __tablename__ = "cost_snapshots"
    __table_args__ = (
        UniqueConstraint("symbol", "snapshot_date", name="uq_cost_snapshots_symbol_date"),
        Index("ix_cost_snapshots_symbol", "symbol"),
        Index("ix_cost_snapshots_sector", "sector"),
        Index("ix_cost_snapshots_snapshot_date", "snapshot_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float)
    total_unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    breakeven_p25: Mapped[float] = mapped_column(Float, nullable=False)
    breakeven_p50: Mapped[float] = mapped_column(Float, nullable=False)
    breakeven_p75: Mapped[float] = mapped_column(Float, nullable=False)
    breakeven_p90: Mapped[float] = mapped_column(Float, nullable=False)
    profit_margin: Mapped[float | None] = mapped_column(Float)
    cost_breakdown: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
