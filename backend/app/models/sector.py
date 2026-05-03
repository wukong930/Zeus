from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SectorAssessment(Base):
    __tablename__ = "sector_assessments"
    __table_args__ = (
        Index("ix_sector_assessments_sector", "sector"),
        Index("ix_sector_assessments_symbol", "symbol"),
        Index("ix_sector_assessments_sector_symbol", "sector", "symbol"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    sector: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    conviction_score: Mapped[float] = mapped_column(Float, nullable=False)
    conviction_direction: Mapped[int] = mapped_column(Integer, nullable=False)
    supporting_factors: Mapped[list] = mapped_column(JSONB, default=list)
    opposing_factors: Mapped[list] = mapped_column(JSONB, default=list)
    data_gaps: Mapped[list] = mapped_column(JSONB, default=list)
    cost_floor: Mapped[float | None] = mapped_column(Float)
    production_margin: Mapped[float | None] = mapped_column(Float)
    inventory_deviation: Mapped[float | None] = mapped_column(Float)
    seasonal_factor: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
