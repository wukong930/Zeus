from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommodityNode(Base):
    __tablename__ = "commodity_nodes"
    __table_args__ = (
        Index("ix_commodity_nodes_cluster", "cluster"),
        Index("ix_commodity_nodes_symbol", "symbol"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    cluster: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    active_alert_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    price_change_24h: Mapped[float | None] = mapped_column(Float)


class RelationshipEdge(Base):
    __tablename__ = "relationship_edges"
    __table_args__ = (
        Index("ix_relationship_edges_source", "source"),
        Index("ix_relationship_edges_target", "target"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commodity_nodes.id", ondelete="cascade"),
        nullable=False,
    )
    target: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commodity_nodes.id", ondelete="cascade"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    active_alert_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    influence_weight: Mapped[float | None] = mapped_column(Float)
    lag_days: Mapped[int | None] = mapped_column(Integer)
    propagation_direction: Mapped[int | None] = mapped_column(Integer)
