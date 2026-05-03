from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShadowRun(Base):
    __tablename__ = "shadow_runs"
    __table_args__ = (
        Index("ix_shadow_runs_status", "status"),
        Index("ix_shadow_runs_algorithm_version", "algorithm_version"),
        Index("ix_shadow_runs_window", "started_at", "ended_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    config_diff: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
