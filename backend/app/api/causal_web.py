from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.industry_data import IndustryData
from app.models.market_data import MarketData
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack
from app.schemas.event_intelligence import EventImpactLinkQualityRead, EventIntelligenceQualityRead
from app.services.data_sources.akshare_futures import COMMODITY_NAMES
from app.services.data_sources.free_ingest import CATEGORY_BY_SYMBOL
from app.services.event_intelligence import evaluate_event_intelligence_quality

router = APIRouter(prefix="/api/causal-web", tags=["causal-web"])

NodeType = Literal["event", "signal", "metric", "alert", "counter"]
EdgeDirection = Literal["bullish", "bearish", "neutral"]
Stage = Literal["source", "thesis", "validation", "impact"]
Sector = Literal[
    "geo",
    "energy",
    "rubber",
    "ferrous",
    "metals",
    "agri",
    "precious",
    "positioning",
]
EventQualityStatus = Literal["blocked", "review", "shadow_ready", "decision_grade"]

SECTOR_BY_CATEGORY = {
    "energy": "energy",
    "chemical": "energy",
    "rubber": "rubber",
    "ferrous": "ferrous",
    "metals": "metals",
    "precious_metals": "precious",
    "agri": "agri",
    "unknown": "geo",
}

STAGE_X: dict[Stage, int] = {
    "source": 70,
    "thesis": 445,
    "validation": 820,
    "impact": 1210,
}
MAX_CAUSAL_EDGES = 24
TYPE_STAGE: dict[NodeType, Stage] = {
    "event": "source",
    "metric": "validation",
    "signal": "thesis",
    "alert": "impact",
    "counter": "validation",
}


class CausalWebEvidenceItem(BaseModel):
    kind: Literal["evidence", "counterevidence"]
    text: str
    textZh: str | None = None
    textEn: str | None = None
    source: str | None = None


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
    labelZh: str | None = None
    labelEn: str | None = None
    narrativeZh: str | None = None
    narrativeEn: str | None = None
    tagsZh: list[str] = Field(default_factory=list)
    tagsEn: list[str] = Field(default_factory=list)
    portfolioLinked: bool = False
    alertLinked: bool = False
    evidence: list[CausalWebEvidenceItem] = Field(default_factory=list)
    counterEvidence: list[CausalWebEvidenceItem] = Field(default_factory=list)
    qualityStatus: EventQualityStatus | None = None
    qualityScore: int | None = Field(default=None, ge=0, le=100)
    qualityIssues: list[str] = Field(default_factory=list)


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
    label_zh: str | None = None
    label_en: str | None = None
    narrative_zh: str | None = None
    narrative_en: str | None = None
    tags_zh: tuple[str, ...] = ()
    tags_en: tuple[str, ...] = ()
    evidence: tuple[CausalWebEvidenceItem, ...] = ()
    counter_evidence: tuple[CausalWebEvidenceItem, ...] = ()
    quality_status: EventQualityStatus | None = None
    quality_score: int | None = None
    quality_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricContext:
    node_id: str
    symbol: str
    category: str


@dataclass(frozen=True)
class CounterContext:
    node_id: str
    alert_id: UUID
    confidence: float


@dataclass(frozen=True)
class EventIntelligenceLinkContext:
    source_node_id: str
    target_node_id: str
    direction: EdgeDirection
    confidence: float
    impact_score: float
    horizon: str
    verified: bool
    quality_status: EventQualityStatus | None = None
    quality_score: int | None = None


@router.get("", response_model=CausalWebGraph)
async def get_causal_web(
    limit: int = Query(default=12, ge=4, le=40),
    symbol: str | None = Query(default=None, min_length=1, max_length=20),
    region: str | None = Query(default=None, min_length=1, max_length=80),
    event_id: UUID | None = Query(default=None, alias="event"),
    session: AsyncSession = Depends(get_db),
) -> CausalWebGraph:
    symbol_filter = _normalize_symbol(symbol) if symbol else None
    pinned_event_item = await session.get(EventIntelligenceItem, event_id) if event_id else None
    if pinned_event_item is not None and pinned_event_item.status == "rejected":
        pinned_event_item = None
    news_limit = max(3, limit // 3)
    news = _unique_recent_news(
        list(
            (
                await session.scalars(
                    select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(news_limit * 4)
                )
            ).all()
        ),
        limit=news_limit,
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
    market_metrics = list(
        (
            await session.scalars(
                _latest_market_metrics_statement(limit=max(6, limit))
            )
        ).all()
    )
    event_intelligence_rows = list(
        (
            await session.scalars(
                _event_intelligence_statement(
                    limit=max(8, min(limit * 4, 64)),
                    symbol=symbol_filter,
                    region=region,
                )
            )
        ).all()
    )
    event_intelligence_items = _unique_recent_event_intelligence(
        _merge_pinned_event_intelligence(
            event_intelligence_rows,
            pinned=pinned_event_item,
        ),
        limit=max(4, min(limit, 16)),
    )
    event_intelligence_links = (
        list(
            (
                await session.scalars(
                    _event_intelligence_link_statement(
                        event_item_ids=[row.id for row in event_intelligence_items],
                        limit=max(6, limit),
                        symbol=symbol_filter,
                        region=region,
                    )
                )
            ).all()
        )
        if event_intelligence_items
        else []
    )
    metric_contexts = [
        *[_metric_context_from_industry(row) for row in metrics],
        *[_metric_context_from_market(row) for row in market_metrics],
    ]
    counter_seeds = [seed for row in alerts for seed in _counter_seeds_from_alert(row)]
    counter_contexts = [
        CounterContext(node_id=seed.id, alert_id=seed.ref_id, confidence=seed.confidence)
        for seed in counter_seeds
        if seed.ref_id is not None
    ]
    event_intelligence_by_id = {row.id: row for row in event_intelligence_items}
    event_intelligence_quality_by_id = _event_intelligence_quality_map(
        event_intelligence_items,
        event_intelligence_links,
    )
    event_intelligence_link_quality_by_id = {
        link_report.id: link_report
        for report in event_intelligence_quality_by_id.values()
        for link_report in report.link_reports
    }
    event_intelligence_link_contexts = _event_intelligence_link_contexts(
        event_intelligence_links,
        event_quality_by_id=event_intelligence_quality_by_id,
        link_quality_by_id=event_intelligence_link_quality_by_id,
    )

    seeds = [
        *[
            _seed_from_event_intelligence_item(row, event_intelligence_quality_by_id.get(row.id))
            for row in event_intelligence_items
        ],
        *[
            _seed_from_event_intelligence_link(
                row,
                event_intelligence_by_id.get(row.event_item_id),
                event_intelligence_link_quality_by_id.get(row.id),
            )
            for row in event_intelligence_links
        ],
        *[_seed_from_news(row) for row in news],
        *[_seed_from_metric(row) for row in metrics],
        *[_seed_from_market_metric(row) for row in market_metrics],
        *[_seed_from_signal(row) for row in signals],
        *counter_seeds,
        *[_seed_from_alert(row) for row in alerts],
    ]
    nodes = _layout_nodes(seeds)
    edges = _build_edges(
        news=news,
        metrics=metric_contexts,
        signals=signals,
        alerts=alerts,
        counters=counter_contexts,
        node_ids={n.id for n in nodes},
        event_intelligence_links=event_intelligence_link_contexts,
    )
    return CausalWebGraph(
        generated_at=datetime.now(timezone.utc),
        nodes=nodes,
        edges=edges,
        source_counts={
            "news": len(news),
            "metrics": len(metrics) + len(market_metrics),
            "signals": len(signals),
            "counters": len(counter_seeds),
            "alerts": len(alerts),
            "event_intelligence": len(event_intelligence_items),
        },
    )


def _seed_from_event_intelligence_item(
    row: EventIntelligenceItem,
    quality: EventIntelligenceQualityRead | None = None,
) -> GraphNodeSeed:
    symbols = [_normalize_symbol(symbol) for symbol in (row.symbols or [])[:3]]
    mechanisms = [str(value) for value in (row.mechanisms or [])[:2]]
    title = _short(row.title, 96)
    summary = _event_summary_text(row.summary or row.title)
    evidence = _compact_event_values(row.evidence)
    counterevidence = _compact_event_values(row.counterevidence)
    evidence_items = _evidence_items(row.evidence, kind="evidence", source=row.source_type)
    counter_evidence_items = _evidence_items(row.counterevidence, kind="counterevidence", source=row.source_type)
    quality_status = quality.status if quality is not None else None
    quality_zh = _event_quality_label_zh(quality_status)
    quality_en = _event_quality_label_en(quality_status)
    quality_score = quality.score if quality is not None else None
    quality_issues = tuple(issue.message for issue in (quality.issues if quality is not None else [])[:3])
    symbol_zh = _join_or(symbols, "未标明", transform=_zh_text)
    symbol_en = _join_or(symbols, "unspecified")
    mechanism_zh = _join_or(mechanisms, "待识别", transform=_zh_text)
    mechanism_en = _join_or(mechanisms, "unclassified", transform=_humanize_token)
    return GraphNodeSeed(
        id=f"ei-{row.id}",
        type="event",
        label=row.title,
        timestamp=row.event_timestamp,
        category=_category_from_symbols(symbols),
        confidence=max(row.confidence, min(row.impact_score / 100, 1.0)),
        direction="neutral",
        tags=tuple(filter(None, (row.event_type, row.status, *symbols[:2], *mechanisms[:1]))),
        narrative=row.summary or row.title,
        alert_linked=quality_status == "decision_grade",
        ref_id=row.id,
        label_zh=f"{_zh_text(row.event_type)}事件：{symbol_zh}",
        label_en=title,
        narrative_zh=(
            f"事件智能源：{_zh_text(summary)}。影响品种：{symbol_zh}；"
            f"作用机制：{mechanism_zh}；证据：{_join_or(evidence, '暂无', transform=_zh_text)}；"
            f"反证：{_join_or(counterevidence, '暂无', transform=_zh_text)}；质量门：{quality_zh}"
            f"{f' {quality_score}/100' if quality_score is not None else ''}。"
        ),
        narrative_en=(
            f"Event intelligence source: {summary}. Impact symbols: {symbol_en}; "
            f"mechanisms: {mechanism_en}; evidence: {_join_or(evidence, 'none')}; "
            f"counter-evidence: {_join_or(counterevidence, 'none')}; quality gate: {quality_en}"
            f"{f' {quality_score}/100' if quality_score is not None else ''}."
        ),
        tags_zh=tuple(
            filter(None, ("事件智能", _zh_text(row.status), quality_zh, mechanism_zh, f"证据 {len(row.evidence or [])}"))
        ),
        tags_en=tuple(
            filter(None, ("Event Intelligence", _humanize_token(row.status), quality_en, mechanism_en, f"evidence {len(row.evidence or [])}"))
        ),
        evidence=evidence_items,
        counter_evidence=counter_evidence_items,
        quality_status=quality_status,
        quality_score=quality_score,
        quality_issues=quality_issues,
    )


def _event_intelligence_quality_map(
    items: list[EventIntelligenceItem],
    links: list[EventImpactLink],
) -> dict[UUID, EventIntelligenceQualityRead]:
    links_by_event_id: dict[UUID, list[EventImpactLink]] = {item.id: [] for item in items}
    for link in links:
        links_by_event_id.setdefault(link.event_item_id, []).append(link)
    return {
        item.id: evaluate_event_intelligence_quality(item, links_by_event_id.get(item.id, []))
        for item in items
    }


def _seed_from_event_intelligence_link(
    row: EventImpactLink,
    event_item: EventIntelligenceItem | None,
    quality: EventImpactLinkQualityRead | None = None,
) -> GraphNodeSeed:
    symbol = _normalize_symbol(row.symbol)
    category = CATEGORY_BY_SYMBOL.get(symbol) or (
        _category_from_symbols([_normalize_symbol(value) for value in (event_item.symbols or [])])
        if event_item is not None
        else "unknown"
    )
    evidence = _compact_event_values(row.evidence or (event_item.evidence if event_item is not None else []))
    counterevidence = _compact_event_values(
        row.counterevidence or (event_item.counterevidence if event_item is not None else [])
    )
    evidence_items = _evidence_items(
        row.evidence or (event_item.evidence if event_item is not None else []),
        kind="evidence",
        source="impact_link",
    )
    counter_evidence_items = _evidence_items(
        row.counterevidence or (event_item.counterevidence if event_item is not None else []),
        kind="counterevidence",
        source="impact_link",
    )
    mechanism_zh = _zh_text(row.mechanism)
    mechanism_en = _humanize_token(row.mechanism)
    direction_zh = _zh_text(row.direction)
    direction_en = _humanize_token(row.direction)
    horizon_zh = _zh_text(row.horizon)
    horizon_en = _humanize_token(row.horizon)
    rationale = _event_summary_text(row.rationale or (event_item.summary if event_item is not None else row.mechanism))
    quality_status: EventQualityStatus | None = (
        _link_quality_to_event_status(quality.status, row.status) if quality else None
    )
    quality_zh = _event_quality_label_zh(quality_status)
    quality_en = _event_quality_label_en(quality_status)
    quality_score = quality.score if quality is not None else None
    quality_issues = tuple(issue.message for issue in (quality.issues if quality is not None else [])[:3])
    return GraphNodeSeed(
        id=f"ei-link-{row.id}",
        type="signal",
        label=f"{symbol} {row.mechanism.replace('_', ' ')}",
        timestamp=row.created_at,
        category=category,
        confidence=max(row.confidence, min(row.impact_score / 100, 1.0)),
        direction=_direction(row.direction),
        tags=tuple(filter(None, (symbol, row.mechanism, row.status, row.region_id, row.horizon))),
        narrative=row.rationale or (event_item.summary if event_item is not None else row.mechanism),
        portfolio_linked=bool(symbol),
        alert_linked=row.status == "confirmed" and quality is not None and quality.passed_gate,
        ref_id=row.id,
        label_zh=f"{symbol} {mechanism_zh}影响假设",
        label_en=f"{symbol} {mechanism_en} impact hypothesis",
        narrative_zh=(
            f"影响假设：{_zh_text(rationale)}。方向：{direction_zh}；"
            f"置信度：{round(row.confidence * 100)}%；影响分：{round(row.impact_score)}；"
            f"周期：{horizon_zh}；证据：{_join_or(evidence, '暂无', transform=_zh_text)}；"
            f"反证：{_join_or(counterevidence, '暂无', transform=_zh_text)}；质量门：{quality_zh}"
            f"{f' {quality_score}/100' if quality_score is not None else ''}。"
        ),
        narrative_en=(
            f"Impact hypothesis: {rationale}. Direction: {direction_en}; "
            f"confidence: {round(row.confidence * 100)}%; impact score: {round(row.impact_score)}; "
            f"horizon: {horizon_en}; evidence: {_join_or(evidence, 'none')}; "
            f"counter-evidence: {_join_or(counterevidence, 'none')}; quality gate: {quality_en}"
            f"{f' {quality_score}/100' if quality_score is not None else ''}."
        ),
        tags_zh=tuple(filter(None, ("事件智能", direction_zh, quality_zh, mechanism_zh, _zh_text(row.status)))),
        tags_en=tuple(filter(None, ("Event Intelligence", direction_en, quality_en, mechanism_en, _humanize_token(row.status)))),
        evidence=evidence_items,
        counter_evidence=counter_evidence_items,
        quality_status=quality_status,
        quality_score=quality_score,
        quality_issues=quality_issues,
    )


def _event_summary_text(value: str | None) -> str:
    value = (value or "").strip()
    return _short(value, 180).rstrip("。.;；") if value else "No summary available"


def _compact_event_values(values: list[str] | None, *, limit: int = 2) -> list[str]:
    compacted: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _short(str(value).strip(), 96)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        compacted.append(text)
        if len(compacted) >= limit:
            break
    return compacted


def _evidence_items(
    values: list[str] | None,
    *,
    kind: Literal["evidence", "counterevidence"],
    source: str | None,
    limit: int = 4,
) -> tuple[CausalWebEvidenceItem, ...]:
    return tuple(
        CausalWebEvidenceItem(
            kind=kind,
            text=text,
            textZh=_zh_text(text),
            textEn=text,
            source=source,
        )
        for text in _compact_event_values(values, limit=limit)
    )


def _join_or(values: list[str], fallback: str, *, transform=None) -> str:
    if not values:
        return fallback
    if transform is not None:
        values = [transform(value) for value in values]
    return " / ".join(values)


def _humanize_token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).replace("_", " ").split())


def _seed_from_news(row: NewsEvent) -> GraphNodeSeed:
    symbols = [str(symbol).upper() for symbol in row.affected_symbols[:3]]
    category = _category_from_symbols(symbols)
    label = row.title_zh or row.title
    narrative = row.summary_zh or row.summary or label
    return GraphNodeSeed(
        id=f"news-{row.id}",
        type="event",
        label=label,
        timestamp=row.published_at,
        category=category,
        confidence=row.llm_confidence,
        direction=_direction(row.direction),
        tags=tuple([row.event_type, row.source, *symbols[:2]]),
        narrative=narrative,
        label_zh=row.title_zh,
        label_en=row.title_original or row.title,
        narrative_zh=row.summary_zh,
        narrative_en=row.summary_original or row.summary,
        alert_linked=not row.requires_manual_confirmation,
        ref_id=row.id,
    )


def _seed_from_metric(row: IndustryData) -> GraphNodeSeed:
    category = CATEGORY_BY_SYMBOL.get(row.symbol, "unknown")
    return GraphNodeSeed(
        id=f"metric-{row.id}",
        type="metric",
        label=f"{row.symbol} {row.data_type}",
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
        label=f"{row.symbol} close {row.close:g}",
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
        label=f"{row.signal_type} / {row.category}",
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
    label = row.title_zh or row.title
    narrative = row.summary_zh or row.one_liner or row.summary or label
    return GraphNodeSeed(
        id=f"alert-{row.id}",
        type="alert",
        label=label,
        timestamp=row.triggered_at,
        category=row.category,
        confidence=row.confidence,
        direction=_direction_from_text(f"{label} {narrative}"),
        tags=tuple(filter(None, (row.type, row.severity, *assets[:2]))),
        narrative=narrative,
        label_zh=row.title_zh,
        label_en=row.title_original or row.title,
        narrative_zh=row.summary_zh,
        narrative_en=row.summary_original or row.summary,
        portfolio_linked=bool(assets),
        alert_linked=True,
        ref_id=row.id,
    )


def _counter_seeds_from_alert(row: Alert) -> list[GraphNodeSeed]:
    raw_items: list[object] = [
        *row.manual_check_items,
        *row.risk_items,
    ]
    if row.invalidation_reason:
        raw_items.append(row.invalidation_reason)
    if not row.adversarial_passed:
        raw_items.append("adversarial validation not passed or not available")
    if row.human_action_required:
        raw_items.append("manual confirmation required before execution")
    if row.confidence < 0.75:
        raw_items.append("confidence below strong emission threshold")

    items = _unique_counter_items(raw_items)
    seeds: list[GraphNodeSeed] = []
    for index, text in enumerate(items[:2], start=1):
        seeds.append(
            GraphNodeSeed(
                id=f"counter-{row.id}-{index}",
                type="counter",
                label=text,
                timestamp=row.triggered_at,
                category=row.category,
                confidence=max(0.3, min(0.95, 1 - row.confidence + 0.25)),
                direction="bearish",
                tags=tuple(filter(None, ("counter", row.severity, row.type))),
                narrative=text,
                portfolio_linked=bool(row.related_assets),
                alert_linked=True,
                ref_id=row.id,
            )
        )
    return seeds


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
                labelZh=seed.label_zh or _zh_label(seed.label, seed.type, seed.tags),
                labelEn=seed.label_en or seed.label,
                narrativeZh=seed.narrative_zh or _zh_text(seed.narrative or seed.label),
                narrativeEn=seed.narrative_en or seed.narrative or seed.label,
                tagsZh=list(seed.tags_zh[:4]) if seed.tags_zh else [_zh_text(tag) for tag in seed.tags[:4]],
                tagsEn=list(seed.tags_en[:4]) if seed.tags_en else list(seed.tags[:4]),
                portfolioLinked=seed.portfolio_linked,
                alertLinked=seed.alert_linked,
                evidence=list(seed.evidence),
                counterEvidence=list(seed.counter_evidence),
                qualityStatus=seed.quality_status,
                qualityScore=seed.quality_score,
                qualityIssues=list(seed.quality_issues),
            )
        )
    return nodes


def _build_edges(
    *,
    news: list[NewsEvent],
    metrics: list[MetricContext],
    signals: list[SignalTrack],
    alerts: list[Alert],
    counters: list[CounterContext],
    node_ids: set[str],
    event_intelligence_links: list[EventIntelligenceLinkContext] | None = None,
) -> list[CausalWebEdge]:
    edges: list[CausalWebEdge] = []
    edge_keys: set[tuple[str, str]] = set()
    news_contexts = []
    for item in news:
        symbols = {str(symbol).upper() for symbol in item.affected_symbols}
        news_contexts.append((item, symbols, _category_from_symbols(list(symbols))))
    signal_by_alert = _latest_signal_by_alert(signals)
    alerts_by_id = {row.id: row for row in alerts}
    alert_symbols_by_id = {
        row.id: {str(asset).upper() for asset in row.related_assets}
        for row in alerts
    }
    for context in event_intelligence_links or []:
        _append_edge(
            edges,
            f"edge-ei-link-{context.source_node_id}-{context.target_node_id}",
            context.source_node_id,
            context.target_node_id,
            context.confidence,
            context.horizon,
            max(context.confidence, min(context.impact_score / 100, 1.0)),
            context.direction,
            context.verified,
            node_ids,
            edge_keys=edge_keys,
        )

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
                edge_keys=edge_keys,
            )

    for item, symbols, category in news_contexts:
        emitted = 0
        for metric in metrics:
            if not _news_matches_metric(symbols, category, metric):
                continue
            _append_edge(
                edges,
                f"edge-news-metric-{item.id}-{metric.node_id}",
                f"news-{item.id}",
                metric.node_id,
                min(0.82, max(0.42, item.llm_confidence)),
                item.time_horizon or "same day",
                0.5,
                _direction(item.direction),
                not item.requires_manual_confirmation,
                node_ids,
                edge_keys=edge_keys,
            )
            emitted += 1
            if emitted >= 2:
                break

    for counter in counters:
        alert = alerts_by_id.get(counter.alert_id)
        if alert is None:
            continue
        _append_edge(
            edges,
            f"edge-counter-alert-{counter.node_id}-{alert.id}",
            counter.node_id,
            f"alert-{alert.id}",
            counter.confidence,
            "review",
            counter.confidence,
            "bearish",
            True,
            node_ids,
            edge_keys=edge_keys,
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
                    edge_keys=edge_keys,
                )
                break
        for item, _, category in news_contexts:
            if category == signal.category:
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
                    edge_keys=edge_keys,
                )
                break

    for item, symbols, _ in news_contexts:
        for alert in alerts:
            if symbols & alert_symbols_by_id[alert.id]:
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
                    edge_keys=edge_keys,
                )
                break
    return _trim_edges(edges, limit=MAX_CAUSAL_EDGES)


def _trim_edges(edges: list[CausalWebEdge], *, limit: int) -> list[CausalWebEdge]:
    if len(edges) <= limit:
        return edges
    ranked = sorted(
        enumerate(edges),
        key=lambda item: (
            -_edge_type_priority(item[1]),
            -int(item[1].verified),
            -item[1].confidence,
            -item[1].hitRate,
            item[0],
        ),
    )
    return [edge for _, edge in ranked[:limit]]


def _edge_type_priority(edge: CausalWebEdge) -> int:
    if edge.id.startswith("edge-signal-alert"):
        return 100
    if edge.id.startswith("edge-ei-link"):
        return 98
    if edge.id.startswith("edge-news-signal"):
        return 95
    if edge.id.startswith("edge-metric-signal"):
        return 90
    if edge.id.startswith("edge-news-alert"):
        return 85
    if edge.id.startswith("edge-news-metric"):
        return 80
    if edge.id.startswith("edge-counter-alert"):
        return 60
    return 50


def _latest_signal_by_alert(signals: list[SignalTrack]) -> dict[UUID, SignalTrack]:
    latest: dict[UUID, SignalTrack] = {}
    for row in signals:
        if row.alert_id is None:
            continue
        current = latest.get(row.alert_id)
        if current is None or _signal_sort_key(row) > _signal_sort_key(current):
            latest[row.alert_id] = row
    return latest


def _signal_sort_key(row: SignalTrack) -> tuple[datetime, float]:
    created_at = row.created_at
    if created_at is None:
        created_at = datetime.min.replace(tzinfo=timezone.utc)
    elif created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    return (created_at, row.confidence)


def _news_matches_metric(symbols: set[str], category: str, metric: MetricContext) -> bool:
    if metric.symbol.upper() in symbols:
        return True
    return category != "unknown" and category == metric.category


def _unique_by_id(rows: list[Alert]) -> list[Alert]:
    seen: set[UUID] = set()
    unique: list[Alert] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique.append(row)
    return unique


def _unique_recent_news(rows: list[NewsEvent], *, limit: int) -> list[NewsEvent]:
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    unique: list[NewsEvent] = []
    for row in rows:
        key = _news_display_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


def _unique_recent_event_intelligence(
    rows: list[EventIntelligenceItem],
    *,
    limit: int,
) -> list[EventIntelligenceItem]:
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    unique: list[EventIntelligenceItem] = []
    for row in rows:
        key = _event_intelligence_display_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


def _merge_pinned_event_intelligence(
    rows: list[EventIntelligenceItem],
    *,
    pinned: EventIntelligenceItem | None,
) -> list[EventIntelligenceItem]:
    if pinned is None:
        return rows
    return [pinned, *[row for row in rows if row.id != pinned.id]]


def _news_display_key(row: NewsEvent) -> tuple[str, tuple[str, ...], str]:
    symbols = tuple(sorted(str(symbol).upper() for symbol in row.affected_symbols[:5]))
    return (row.event_type.lower(), symbols, _normalize_news_title(row.title))


def _event_intelligence_display_key(row: EventIntelligenceItem) -> tuple[str, tuple[str, ...], str]:
    symbols = tuple(sorted(str(symbol).upper() for symbol in (row.symbols or [])[:5]))
    return (row.event_type.lower(), symbols, _normalize_news_title(row.title))


def _normalize_news_title(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^\s*\([^)]*\)\s*", "", normalized)
    normalized = re.sub(r"^\s*feature\s*:\s*", "", normalized)
    normalized = normalized.split("--", 1)[0]
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return " ".join(normalized.split())


def _latest_market_metrics_statement(*, limit: int):
    ranked = (
        select(
            MarketData.id.label("id"),
            func.row_number()
            .over(
                partition_by=MarketData.symbol,
                order_by=(
                    MarketData.ingested_at.desc(),
                    MarketData.timestamp.desc(),
                    MarketData.vintage_at.desc(),
                ),
            )
            .label("rn"),
        )
        .select_from(MarketData)
        .subquery()
    )

    return (
        select(MarketData)
        .join(ranked, MarketData.id == ranked.c.id)
        .where(ranked.c.rn == 1)
        .order_by(MarketData.ingested_at.desc(), MarketData.timestamp.desc())
        .limit(limit)
    )


def _event_intelligence_statement(
    *,
    limit: int,
    symbol: str | None,
    region: str | None,
):
    statement = (
        select(EventIntelligenceItem)
        .where(EventIntelligenceItem.status != "rejected")
        .order_by(EventIntelligenceItem.event_timestamp.desc(), EventIntelligenceItem.created_at.desc())
        .limit(limit)
    )
    if symbol:
        statement = statement.where(EventIntelligenceItem.symbols.contains([symbol]))
    if region:
        statement = statement.where(EventIntelligenceItem.regions.contains([region]))
    return statement


def _event_intelligence_link_statement(
    *,
    event_item_ids: list[UUID],
    limit: int,
    symbol: str | None,
    region: str | None,
):
    statement = (
        select(EventImpactLink)
        .where(
            EventImpactLink.event_item_id.in_(event_item_ids),
            EventImpactLink.status != "rejected",
        )
        .order_by(EventImpactLink.impact_score.desc(), EventImpactLink.confidence.desc())
        .limit(limit)
    )
    if symbol:
        statement = statement.where(EventImpactLink.symbol == symbol)
    if region:
        statement = statement.where(or_(EventImpactLink.region_id == region, EventImpactLink.region_id.is_(None)))
    return statement


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


def _event_intelligence_link_contexts(
    rows: list[EventImpactLink],
    *,
    event_quality_by_id: dict[UUID, EventIntelligenceQualityRead] | None = None,
    link_quality_by_id: dict[UUID, EventImpactLinkQualityRead] | None = None,
) -> list[EventIntelligenceLinkContext]:
    contexts: list[EventIntelligenceLinkContext] = []
    for row in rows:
        event_quality = (event_quality_by_id or {}).get(row.event_item_id)
        link_quality = (link_quality_by_id or {}).get(row.id)
        verified = (
            _event_intelligence_verified(row.status)
            and event_quality is not None
            and event_quality.decision_grade
            and link_quality is not None
            and link_quality.passed_gate
        )
        contexts.append(
            EventIntelligenceLinkContext(
                source_node_id=f"ei-{row.event_item_id}",
                target_node_id=f"ei-link-{row.id}",
                direction=_direction(row.direction),
                confidence=row.confidence,
                impact_score=row.impact_score,
                horizon=row.horizon or "short",
                verified=verified,
            quality_status=(
                _link_quality_to_event_status(link_quality.status, row.status)
                if link_quality is not None
                else None
            ),
                quality_score=link_quality.score if link_quality is not None else None,
            )
        )
    return contexts


def _unique_counter_items(items: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _counter_item_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _counter_item_text(item: object) -> str:
    if isinstance(item, str):
        return " ".join(item.split())
    if isinstance(item, dict):
        for key in ("title", "summary", "reason", "message", "check", "item", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        if item:
            return _short(" ".join(f"{key}: {value}" for key, value in item.items()), 120)
    return ""


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
    *,
    edge_keys: set[tuple[str, str]] | None = None,
) -> None:
    if source not in node_ids or target not in node_ids or source == target:
        return
    edge_key = (source, target)
    if edge_keys is not None:
        if edge_key in edge_keys:
            return
        edge_keys.add(edge_key)
    else:
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


def _event_intelligence_verified(status: str | None) -> bool:
    return status in {"confirmed", "validated", "applied"}


def _link_quality_to_event_status(
    status: str | None,
    governance_status: str | None = None,
) -> EventQualityStatus | None:
    if status == "passed":
        if _event_intelligence_verified(governance_status):
            return "decision_grade"
        return "shadow_ready"
    if status == "review":
        return "review"
    if status == "blocked":
        return "blocked"
    return None


def _event_quality_label_zh(status: EventQualityStatus | None) -> str:
    return {
        "blocked": "质量阻断",
        "review": "质量复核",
        "shadow_ready": "影子可用",
        "decision_grade": "决策级",
        None: "未评估",
    }[status]


def _event_quality_label_en(status: EventQualityStatus | None) -> str:
    return {
        "blocked": "blocked",
        "review": "quality review",
        "shadow_ready": "shadow ready",
        "decision_grade": "decision grade",
        None: "not evaluated",
    }[status]


def _normalize_symbol(value: str) -> str:
    return str(value).upper().strip()


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


_TEXT_ZH_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Check whether high-cost producers are already cutting operating rates.", "检查高成本生产者是否已经降低开工率。"),
    ("high-cost producers", "高成本生产者"),
    ("cutting operating rates", "降低开工率"),
    ("Check whether", "检查是否"),
    ("adversarial validation not passed or not available", "对抗校验未通过或暂无结果"),
    ("manual confirmation required before execution", "执行前需要人工确认"),
    ("confidence below strong emission threshold", "置信度低于强触发阈值"),
    ("regime shift", "状态切换"),
    ("inventory shock", "库存冲击"),
    ("cost support", "成本支撑"),
    ("price gap", "价差偏离"),
    ("precious metals", "贵金属"),
    ("regime_shift", "状态切换"),
    ("inventory_shock", "库存冲击"),
    ("cost_support", "成本支撑"),
    ("momentum", "动量"),
    ("price_gap", "价差偏离"),
    ("weather", "天气"),
    ("supply", "供应"),
    ("demand", "需求"),
    ("inventory", "库存"),
    ("metals", "有色"),
    ("agri", "农产"),
    ("chemical", "能化"),
    ("geopolitical", "地缘"),
    ("policy", "政策"),
    ("breaking", "突发"),
    ("single source", "单一来源"),
    ("cross verified", "交叉验证"),
    ("validation", "校验"),
    ("event intelligence", "事件智能"),
    ("human review", "人工复核"),
    ("shadow review", "影子复核"),
    ("confirmed", "已确认"),
    ("logistics", "物流"),
    ("risk sentiment", "风险情绪"),
    ("macro", "宏观"),
    ("horizon", "周期"),
    ("confidence", "置信度"),
    ("outcome", "结果"),
    ("regime", "状态"),
    ("pending", "待观察"),
    ("alert", "预警"),
    ("signal", "信号"),
    ("source", "来源"),
    ("close", "收盘"),
    ("volume", "成交量"),
    ("latest", "最新"),
    ("review", "复核"),
    ("watch", "观察"),
    ("short", "短期"),
    ("medium", "中期"),
    ("long", "长期"),
    ("southeast asia rubber", "东南亚橡胶产区"),
    ("middle east crude", "中东原油链路"),
    ("bullish", "偏多"),
    ("bearish", "偏空"),
    ("neutral", "中性"),
)


def _zh_label(value: str, node_type: NodeType, tags: tuple[str, ...] = ()) -> str:
    if node_type == "event":
        event_type = _zh_text(tags[0]) if tags else "外部"
        symbols = [_zh_text(tag) for tag in tags[2:] if tag]
        suffix = f"：{' / '.join(symbols)}" if symbols else ""
        return f"{event_type}事件{suffix}"
    text = _zh_text(value)
    if _contains_cjk(text):
        return text
    if node_type == "metric":
        return f"指标：{text}"
    if node_type == "signal":
        return f"信号：{text}"
    if node_type == "alert":
        return f"预警：{text}"
    if node_type == "counter":
        return f"反证：{text}"
    return text


def _zh_text(value: str) -> str:
    if not value:
        return value
    result = value.replace("_", " ")
    for symbol, name in sorted(COMMODITY_NAMES.items(), key=lambda item: len(item[0]), reverse=True):
        result = _replace_token(result, symbol, name)
    for source, target in _TEXT_ZH_REPLACEMENTS:
        result = _replace_phrase(result, source, target)
    return " ".join(result.split())


def _replace_token(value: str, source: str, target: str) -> str:
    return _replace_phrase(value, source, target, token=True)


def _replace_phrase(value: str, source: str, target: str, *, token: bool = False) -> str:
    escaped = re.escape(source)
    pattern = rf"\b{escaped}\b" if token else escaped
    return re.sub(pattern, target, value, flags=re.IGNORECASE)


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _short(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1]}..."
