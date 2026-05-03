from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.core.database import Base


class PgVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):
        def process(value: Sequence[float] | str | None) -> str | None:
            if value is None or isinstance(value, str):
                return value
            return "[" + ",".join(f"{float(item):.8f}" for item in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value: str | None) -> list[float] | None:
            if value is None:
                return None
            raw = value.strip()
            if raw.startswith("[") and raw.endswith("]"):
                raw = raw[1:-1]
            if not raw:
                return []
            return [float(item) for item in raw.split(",")]

        return process


class VectorChunk(Base):
    __tablename__ = "vector_chunks"
    __table_args__ = (
        Index("ix_vector_chunks_chunk_type", "chunk_type"),
        Index("ix_vector_chunks_source_id", "source_id"),
        Index("ix_vector_chunks_quality_status", "quality_status"),
        Index("ix_vector_chunks_created_at", "created_at"),
        Index("ix_vector_chunks_metadata", "metadata", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(PgVector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    quality_status: Mapped[str] = mapped_column(String(20), default="unverified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
