from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContractMetadata(Base):
    __tablename__ = "contract_metadata"
    __table_args__ = (
        UniqueConstraint("symbol", "contract_month", name="uq_contract_symbol_month"),
        Index("ix_contract_metadata_symbol", "symbol"),
        Index("ix_contract_metadata_is_main", "symbol", "is_main"),
        Index("ix_contract_metadata_expiry", "expiry_date"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(20))
    commodity: Mapped[str | None] = mapped_column(Text)
    contract_month: Mapped[str] = mapped_column(String(20), nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    main_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    main_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    volume: Mapped[float | None] = mapped_column(Float)
    open_interest: Mapped[float | None] = mapped_column(Float)
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
