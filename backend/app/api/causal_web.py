from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.industry_data import IndustryData
from app.models.market_data import MarketData
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack
from app.services.data_sources.free_ingest import CATEGORY_BY_SYMBOL

router = APIRouter(prefix="/api/causal-web", tags=["causal-web"])

NodeType = Literal["event", "signal", "metric", "alert", "counter"]
EdgeDirection = Literal["bullish", "bearish", "neutral"]
Stage = Literal["source", "thesis", "validation", "impact"]
Sector = Literal["geo", "energy", "rubber", "ferrous", "positioning"]

SECTOR_BY_CATEGORY = {
    "energy": "energy",
    "chemical": "energy",
    "rubber": "rubber",
    "ferrous": "ferrous",
    "metals": "ferrous",
    "precious_metals": "ferrous",
    "agri": "rubber",
    "unknown": "geo",
}

STAGE_X: dict[Stage, int] = {
    "source": 70,
    "thesis": 445,
    "validation": 820,
    "impact": 1210,
}
TYPE_STAGE: dict[NodeType, Stage] = {
    "event": "source",
    "metric": "validation",
    "signal": "thesis",
    "alert": "impact",
    "counter": "validation",
}


class CausalWebNode(BaseModel):
    id: str
    type: NodeType
    label: str
    freshness: float = Field(ge=0, le=1)
    influence: Literal[1, 2, 3, 4]
    active: bool
    x: int
    y: int
    stage: Stage
    sector: Sector
    tags: list[str] = Field(default_factory=list)
    narrative: str
    portfolioLinked: bool = False
    alertLinked: bool = False


class CausalWebEdge(BaseModel):
    id: str
    source: str
    target: str
    confidence: float = Field(ge=0, le=1)
    lag: str
    hitRate: float = Field(ge=0, le=1)
    direction: EdgeDirection
    verified: bool


class CausalWebGraph(BaseModel):
    generated_at: datetime
    nodes: list[CausalWebNode]
    edges: list[CausalWebEdge]
    source_counts: dict[str, int]


@dataclass(frozen=True)
class GraphNodeSeed:
    id: str
    type: NodeType
    label: str
    timestamp: datetime
    category: str
    confidence: float
    direction: EdgeDirection = "neutral"
    tags: tuple[str, ...] = ()
    narrative: str | None = None
    portfolio_linked: bool = False
    alert_linked: bool = False
    ref_id: UUID | None = None


@dataclass(frozen=True)
class MetricContext:
    node_id: str
    symbol: str
    category: str


@router.get("", response_model=CausalWebGraph)
async def get_causal_web(
    limit: int = Query(default=12, ge=4, le=40),
    session: AsyncSession = Depends(get_db),
) -> CausalWebGraph:
    news = list(
        (
            await session.scalars(
                select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(max(3, limit // 3))
            )
        ).all()
    )
    signals = list(
        (
            await session.scalars(
                select(SignalTrack).order_by(SignalTrack.created_at.desc()).limit(limit)
            )
        ).all()
    )
    recent_alerts = list(
        (
            await session.scalars(
                select(Alert)
                .where(Alert.status != "suppressed")
                .order_by(Alert.triggered_at.desc())
                .limit(max(4, limit // 2))
            )
        ).all()
    )
    linked_alert_ids = [row.alert_id for row in signals if row.alert_id is not None]
    linked_alerts = (
        list((await session.scalars(select(Alert).where(Alert.id.in_(linked_alert_ids)))).all())
        if linked_alert_ids
        else []
    )
    alerts = _unique_by_id([*recent_alerts, *linked_alerts])[:limit]
    metrics = list(
        (
            await session.scalars(
                select(IndustryData).order_by(IndustryData.ingested_at.desc()).limit(max(4, limit // 2))
            )
        ).all()
    )
    market_metrics = _latest_market_metrics(
        list(
            (
                await session.scalars(
                    select(MarketData).order_by(MarketData.ingested_at.desc()).limit(limit * 240)
                )
            ).all()
        ),
        limit=max(6, limit),
    )
    metric_contexts = [
        *[_metric_context_from_industry(row) for row in metrics],
        *[_metric_context_from_market(row) for row in market_metrics],
    ]

    seeds = [
        *[_seed_from_news(row) for row in news],
        *[_seed_from_metric(row) for row in metrics],
        *[_seed_from_market_metric(row) for row in market_metrics],
        *[_seed_from_signal(row) for row in signals],
        *[_seed_from_alert(row) for row in alerts],
    ]
    nodes = _layout_nodes(seeds)
    edges = _build_edges(
        news=news,
        metrics=metric_contexts,
        signals=signals,
        alerts=alerts,
        node_ids={n.id for n in nodes},
    )
    return CausalWebGraph(
        generated_at=datetime.now(timezone.utc),
        nodes=nodes,
        edges=edges,
        source_counts={
            "news": len(news),
            "metrics": len(metrics) + len(market_metrics),
            "signals": len(signals),
            "alerts": len(alerts),
        },
    )


def _seed_from_news(row: NewsEvent) -> GraphNodeSeed:
    symbols = [str(symbol).upper() for symbol in row.affected_symbols[:3]]
    category = _category_from_symbols(symbols)
    return GraphNodeSeed(
        id=f"news-{row.id}",
        type="event",
        label=_short(row.title, 18),
        timestamp=row.published_at,
        category=category,
        confidence=row.llm_confidence,
        direction=_direction(row.direction),
        tags=tuple([row.event_type, row.source, *symbols[:2]]),
        narrative=row.summary or row.title,
        alert_linked=not row.requires_manual_confirmation,
        ref_id=row.id,
    )


def _seed_from_metric(row: IndustryData) -> GraphNodeSeed:
    category = CATEGORY_BY_SYMBOL.get(row.symbol, "unknown")
    return GraphNodeSeed(
        id=f"metric-{row.id}",
        type="metric",
        label=_short(f"{row.symbol} {row.data_type}", 18),
        timestamp=row.timestamp,
        category=category,
        confidence=0.65,
        tags=(row.symbol, row.source, row.unit),
        narrative=f"{row.source} {row.data_type}: {row.value:g} {row.unit}",
        ref_id=row.id,
    )


def _seed_from_market_metric(row: MarketData) -> GraphNodeSeed:
    category = CATEGORY_BY_SYMBOL.get(row.symbol, "unknown")
    return GraphNodeSeed(
        id=f"metric-market-{row.id}",
        type="metric",
        label=_short(f"{row.symbol} close {row.close:g}", 18),
        timestamp=row.timestamp,
        category=category,
        confidence=0.7,
        tags=(row.symbol, row.exchange, row.contract_month),
        narrative=f"{row.symbol} latest close {row.close:g}; volume {row.volume:g}",
        ref_id=row.id,
    )


def _seed_from_signal(row: SignalTrack) -> GraphNodeSeed:
    return GraphNodeSeed(
        id=f"signal-{row.id}",
        type="signal",
        label=_short(f"{row.signal_type} / {row.category}", 18),
        timestamp=row.created_at,
        category=row.category,
        confidence=row.confidence,
        direction="neutral",
        tags=tuple(filter(None, (row.signal_type, row.category, row.regime_at_emission))),
        narrative=(
            f"{row.signal_type} confidence {row.confidence:.0%}; "
            f"outcome={row.outcome}; regime={row.regime_at_emission or row.regime or 'unknown'}"
        ),
        alert_linked=row.alert_id is not None,
        ref_id=row.id,
    )


def _seed_from_alert(row: Alert) -> GraphNodeSeed:
    assets = [str(asset).upper() for asset in row.related_assets[:3]]
    return GraphNodeSeed(
        id=f"alert-{row.id}",
        type="alert",
        label=_short(row.title, 18),
        timestamp=row.triggered_at,
        category=row.category,
        confidence=row.confidence,
        direction=_direction_from_text(f"{row.title} {row.summary}"),
        tags=tuple(filter(None, (row.type, row.severity, *assets[:2]))),
        narrative=row.one_liner or row.summary or row.title,
        portfolio_linked=bool(assets),
        alert_linked=True,
        ref_id=row.id,
    )


def _layout_nodes(seeds: list[GraphNodeSeed]) -> list[CausalWebNode]:
    lanes: dict[Stage, int] = {"source": 0, "thesis": 0, "validation": 0, "impact": 0}
    nodes: list[CausalWebNode] = []
    for seed in seeds:
        stage = TYPE_STAGE[seed.type]
        lane = lanes[stage]
        lanes[stage] += 1
        sector = _sector(seed.category)
        nodes.append(
            CausalWebNode(
                id=seed.id,
                type=seed.type,
                label=seed.label,
                freshness=_freshness(seed.timestamp),
                influence=_influence(seed.type, seed.confidence),
                active=_freshness(seed.timestamp) > 0.35 or seed.type == "alert",
                x=STAGE_X[stage],
                y=90 + lane * 150 + (40 if stage in {"thesis", "impact"} else 0),
                stage=stage,
                sector=sector,
                tags=list(seed.tags[:4]),
                narrative=seed.narrative or seed.label,
                portfolioLinked=seed.portfolio_linked,
                alertLinked=seed.alert_linked,
            )
        )
    return nodes


def _build_edges(
    *,
    news: list[NewsEvent],
    metrics: list[MetricContext],
    signals: list[SignalTrack],
    alerts: list[Alert],
    node_ids: set[str],
) -> list[CausalWebEdge]:
    edges: list[CausalWebEdge] = []
    signal_by_alert = {row.alert_id: row for row in signals if row.alert_id is not None}
    for alert in alerts:
        signal = signal_by_alert.get(alert.id)
        if signal is not None:
            _append_edge(
                edges,
                f"edge-signal-alert-{signal.id}-{alert.id}",
                f"signal-{signal.id}",
                f"alert-{alert.id}",
                signal.confidence,
                "0-5m",
                signal.confidence,
                _direction_from_text(f"{alert.title} {alert.summary}"),
                True,
                node_ids,
            )

    for signal in signals[:8]:
        for item in metrics:
            if signal.category == item.category:
                _append_edge(
                    edges,
                    f"edge-metric-signal-{item.node_id}-{signal.id}",
                    item.node_id,
                    f"signal-{signal.id}",
                    min(0.88, max(0.35, signal.confidence)),
                    "same day",
                    0.55,
                    "neutral",
                    True,
                    node_ids,
                )
                break
        for item in news:
            symbols = [str(symbol).upper() for symbol in item.affected_symbols]
            if _category_from_symbols(symbols) == signal.category:
                _append_edge(
                    edges,
                    f"edge-news-signal-{item.id}-{signal.id}",
                    f"news-{item.id}",
                    f"signal-{signal.id}",
                    min(0.92, max(item.llm_confidence, signal.confidence)),
                    item.time_horizon,
                    signal.confidence,
                    _direction(item.direction),
                    not item.requires_manual_confirmation,
                    node_ids,
                )
                break

    for item in news:
        for alert in alerts:
            if set(str(symbol).upper() for symbol in item.affected_symbols) & set(
                str(asset).upper() for asset in alert.related_assets
            ):
                _append_edge(
                    edges,
                    f"edge-news-alert-{item.id}-{alert.id}",
                    f"news-{item.id}",
                    f"alert-{alert.id}",
                    item.llm_confidence,
                    item.time_horizon,
                    alert.confidence,
                    _direction(item.direction),
                    not item.requires_manual_confirmation,
                    node_ids,
                )
                break
    return edges[:24]


def _unique_by_id(rows: list[Alert]) -> list[Alert]:
    seen: set[UUID] = set()
    unique: list[Alert] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique.append(row)
    return unique


def _latest_market_metrics(rows: list[MarketData], *, limit: int) -> list[MarketData]:
    seen: set[str] = set()
    latest: list[MarketData] = []
    for row in rows:
        if row.symbol in seen:
            continue
        seen.add(row.symbol)
        latest.append(row)
        if len(latest) >= limit:
            break
    return latest


def _metric_context_from_industry(row: IndustryData) -> MetricContext:
    symbol = str(row.symbol).upper()
    return MetricContext(
        node_id=f"metric-{row.id}",
        symbol=symbol,
        category=CATEGORY_BY_SYMBOL.get(symbol, "unknown"),
    )


def _metric_context_from_market(row: MarketData) -> MetricContext:
    symbol = str(row.symbol).upper()
    return MetricContext(
        node_id=f"metric-market-{row.id}",
        symbol=symbol,
        category=CATEGORY_BY_SYMBOL.get(symbol, "unknown"),
    )


def _append_edge(
    edges: list[CausalWebEdge],
    edge_id: str,
    source: str,
    target: str,
    confidence: float,
    lag: str,
    hit_rate: float,
    direction: EdgeDirection,
    verified: bool,
    node_ids: set[str],
) -> None:
    if source not in node_ids or target not in node_ids or source == target:
        return
    if any(edge.source == source and edge.target == target for edge in edges):
        return
    edges.append(
        CausalWebEdge(
            id=edge_id,
            source=source,
            target=target,
            confidence=max(0.1, min(1.0, confidence)),
            lag=lag,
            hitRate=max(0.1, min(1.0, hit_rate)),
            direction=direction,
            verified=verified,
        )
    )


def _category_from_symbols(symbols: list[str]) -> str:
    for symbol in symbols:
        if category := CATEGORY_BY_SYMBOL.get(symbol):
            return category
    return "unknown"


def _sector(category: str) -> Sector:
    return SECTOR_BY_CATEGORY.get(category, "geo")  # type: ignore[return-value]


def _direction(value: str | None) -> EdgeDirection:
    if value == "bullish":
        return "bullish"
    if value == "bearish":
        return "bearish"
    return "neutral"


def _direction_from_text(text: str) -> EdgeDirection:
    lowered = text.lower()
    if any(marker in lowered for marker in ("bearish", "short", "下行", "偏空", "回落")):
        return "bearish"
    if any(marker in lowered for marker in ("bullish", "long", "上行", "偏多", "上涨", "走强")):
        return "bullish"
    return "neutral"


def _freshness(timestamp: datetime) -> float:
    current = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - current.astimezone(timezone.utc)).total_seconds() / 3600)
    return max(0.08, min(1.0, 1 - age_hours / 72))


def _influence(node_type: NodeType, confidence: float) -> Literal[1, 2, 3, 4]:
    if node_type == "alert" or confidence >= 0.85:
        return 4
    if confidence >= 0.68:
        return 3
    if confidence >= 0.45:
        return 2
    return 1


def _short(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1]}..."
