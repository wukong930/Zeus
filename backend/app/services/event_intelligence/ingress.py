from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.models.industry_data import IndustryData
from app.models.news_events import NewsEvent
from app.models.signal import SignalTrack
from app.services.data_sources.open_meteo import DEFAULT_WEATHER_LOCATIONS
from app.services.event_intelligence.governance import record_event_intelligence_audit
from app.services.event_intelligence.profiles import profile_for_symbol
from app.services.event_intelligence.resolver import (
    EventImpactLinkDraft,
    EventIntelligenceDraft,
    create_event_intelligence_from_draft,
    resolve_news_event_impacts,
)
from app.services.translation.market import category_label, mechanism_label, signal_type_label

WEATHER_DATA_TYPES = frozenset(
    {
        "weather_precip_7d",
        "weather_temp_max_7d",
        "weather_temp_min_7d",
        "weather_baseline_precip_7d",
        "weather_baseline_temp_mean_7d",
        "weather_precip_pctile_7d",
        "weather_temp_pctile_7d",
        "weather_precip_1h",
        "weather_temp_current_c",
        "weather_humidity_pct",
        "weather_wind_kph",
    }
)
WEATHER_REGION_BY_LOCATION_KEY = {
    location.key: location.region_id
    for location in DEFAULT_WEATHER_LOCATIONS
    if location.region_id is not None
}
CATEGORY_SYMBOLS: dict[str, tuple[str, ...]] = {
    "rubber": ("RU", "NR", "BR"),
    "ferrous": ("RB", "HC", "I", "J", "JM"),
    "energy": ("SC",),
    "chemical": ("TA", "MA", "PP"),
    "metals": ("CU", "AL", "ZN", "NI"),
    "nonferrous": ("CU", "AL", "ZN", "NI"),
    "agri": ("M", "Y", "P"),
    "agriculture": ("M", "Y", "P"),
    "precious_metals": ("AU", "AG"),
}


@dataclass(frozen=True)
class EventIntelligenceSyncResult:
    news_scanned: int = 0
    news_created: int = 0
    weather_candidates: int = 0
    weather_created: int = 0
    weather_existing: int = 0
    market_scanned: int = 0
    market_candidates: int = 0
    market_created: int = 0
    market_existing: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "degraded" if self.errors else "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "news_scanned": self.news_scanned,
            "news_created": self.news_created,
            "weather_candidates": self.weather_candidates,
            "weather_created": self.weather_created,
            "weather_existing": self.weather_existing,
            "market_scanned": self.market_scanned,
            "market_candidates": self.market_candidates,
            "market_created": self.market_created,
            "market_existing": self.market_existing,
            "errors": self.errors,
        }


async def sync_event_intelligence_inputs(
    session: AsyncSession,
    *,
    limit: int = 100,
    weather_row_limit: int = 4000,
    market_signal_limit: int = 120,
    now: datetime | None = None,
) -> EventIntelligenceSyncResult:
    observed_at = _ensure_tz(now or datetime.now(UTC))
    errors: list[dict[str, str]] = []

    news_scanned, news_created = await _sync_news_events(session, limit=limit, errors=errors)
    weather_candidates = weather_event_candidates_from_industry_rows(
        await _load_weather_rows(session, limit=weather_row_limit),
        now=observed_at,
        max_candidates=limit,
    )
    weather_created, weather_existing = await _create_candidates(
        session,
        weather_candidates,
        actor="event-intelligence-sync",
        action="ingress.weather",
        note="Low-frequency sync created a weather event intelligence candidate.",
        errors=errors,
    )

    signal_rows = await _load_market_signal_rows(session, limit=market_signal_limit)
    market_candidates = [
        candidate
        for row in signal_rows
        if (candidate := market_signal_event_candidate(row, now=observed_at)) is not None
    ][:limit]
    market_created, market_existing = await _create_candidates(
        session,
        market_candidates,
        actor="event-intelligence-sync",
        action="ingress.market",
        note="Low-frequency sync created a market-anomaly event intelligence candidate.",
        errors=errors,
    )

    return EventIntelligenceSyncResult(
        news_scanned=news_scanned,
        news_created=news_created,
        weather_candidates=len(weather_candidates),
        weather_created=weather_created,
        weather_existing=weather_existing,
        market_scanned=len(signal_rows),
        market_candidates=len(market_candidates),
        market_created=market_created,
        market_existing=market_existing,
        errors=errors,
    )


def weather_event_candidates_from_industry_rows(
    rows: list[IndustryData],
    *,
    now: datetime | None = None,
    max_candidates: int = 100,
) -> list[tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]]]:
    observed_at = _ensure_tz(now or datetime.now(UTC))
    grouped: dict[tuple[str, str], dict[str, IndustryData]] = {}
    for row in rows:
        if row.data_type not in WEATHER_DATA_TYPES:
            continue
        symbol = _root_symbol(row.symbol)
        region_id = _weather_row_region(row) or _primary_region(symbol)
        if not symbol or not region_id:
            continue
        key = (symbol, region_id)
        by_type = grouped.setdefault(key, {})
        previous = by_type.get(row.data_type)
        if previous is None or _industry_row_sort_key(row) > _industry_row_sort_key(previous):
            by_type[row.data_type] = row

    candidates: list[tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]]] = []
    for (symbol, region_id), by_type in grouped.items():
        candidate = weather_event_candidate(symbol, region_id, by_type, now=observed_at)
        if candidate is not None:
            candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (item[0].impact_score, item[0].confidence),
        reverse=True,
    )[:max_candidates]


def weather_event_candidate(
    symbol: str,
    region_id: str,
    rows_by_type: dict[str, IndustryData],
    *,
    now: datetime | None = None,
) -> tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]] | None:
    observed_at = _ensure_tz(now or datetime.now(UTC))
    precip = _row_value(rows_by_type, "weather_precip_7d")
    baseline_precip = _row_value(rows_by_type, "weather_baseline_precip_7d")
    precip_pctile = _row_value(rows_by_type, "weather_precip_pctile_7d")
    temp_pctile = _row_value(rows_by_type, "weather_temp_pctile_7d")
    temp_max = _row_value(rows_by_type, "weather_temp_max_7d")
    temp_min = _row_value(rows_by_type, "weather_temp_min_7d")
    baseline_temp = _row_value(rows_by_type, "weather_baseline_temp_mean_7d")
    precip_1h = _row_value(rows_by_type, "weather_precip_1h")
    current_temp = _row_value(rows_by_type, "weather_temp_current_c")
    wind = _row_value(rows_by_type, "weather_wind_kph")

    precip_anomaly = _pct_change(precip, baseline_precip)
    temp_mean = (temp_max + temp_min) / 2 if temp_max is not None and temp_min is not None else None
    temp_anomaly = (
        round(temp_mean - baseline_temp, 2)
        if temp_mean is not None and baseline_temp is not None
        else None
    )
    trigger = _weather_trigger(
        precip_anomaly=precip_anomaly,
        precip_pctile=precip_pctile,
        precip_1h=precip_1h,
        temp_anomaly=temp_anomaly,
        temp_pctile=temp_pctile,
    )
    if trigger is None:
        return None

    latest_timestamp = max(
        (_ensure_tz(row.timestamp) for row in rows_by_type.values()),
        default=observed_at,
    )
    confidence = _weather_confidence(
        trigger_score=trigger["score"],
        has_baseline=baseline_precip is not None or baseline_temp is not None,
        has_percentile=precip_pctile is not None or temp_pctile is not None,
        has_current=precip_1h is not None or current_temp is not None or wind is not None,
    )
    mechanisms = _weather_mechanisms(trigger["kind"])
    direction = "bullish" if _weather_sensitive(symbol) else "watch"
    evidence = _weather_evidence(
        precip=precip,
        baseline_precip=baseline_precip,
        precip_anomaly=precip_anomaly,
        precip_pctile=precip_pctile,
        precip_1h=precip_1h,
        temp_anomaly=temp_anomaly,
        temp_pctile=temp_pctile,
        current_temp=current_temp,
        wind=wind,
    )
    counterevidence = _compact(
        [
            "天气异常仍需和未来预报路径、现货成交与库存变化交叉验证。",
            "单一气象指标不能直接等同于产量或价格已经发生同向变化。",
            "缺少历史 baseline 行。" if baseline_precip is None and baseline_temp is None else "",
        ]
    )
    source_id = f"weather:{region_id}:{symbol}:{latest_timestamp.date().isoformat()}"
    title = f"天气异常：{symbol} / {region_id}"
    summary = f"{trigger['label']}，可能通过 {', '.join(mechanisms)} 影响 {symbol}。"
    draft = EventIntelligenceDraft(
        source_type="weather",
        source_id=source_id[:80],
        title=title,
        summary=summary,
        event_type="weather",
        event_timestamp=latest_timestamp,
        entities=[region_id],
        symbols=[symbol],
        regions=[region_id],
        mechanisms=mechanisms,
        evidence=evidence,
        counterevidence=counterevidence,
        confidence=confidence,
        impact_score=round(confidence * 100, 2),
        status="shadow_review",
        requires_manual_confirmation=False,
        source_reliability=0.72 if len(_source_families(rows_by_type.values())) > 1 else 0.62,
        freshness_score=_freshness_score(latest_timestamp, observed_at),
        source_payload={
            "resolver_version": "event-intelligence-ingress-v1",
            "trigger": trigger,
            "data_types": sorted(rows_by_type),
            "sources": sorted(_source_families(rows_by_type.values())),
            "production_effect": "none",
        },
    )
    links = [
        EventImpactLinkDraft(
            symbol=symbol,
            region_id=region_id,
            mechanism=mechanism,
            direction=direction,
            confidence=round(confidence * (1.0 if mechanism == "weather" else 0.86), 4),
            impact_score=round(confidence * (100 if mechanism == "weather" else 86), 2),
            horizon="short",
            rationale=f"{symbol} 对{mechanism_label(mechanism)}机制敏感，{trigger['label']} 进入事件智能候选链。",
            evidence=tuple(evidence),
            counterevidence=tuple(counterevidence),
            status="shadow_review",
        )
        for mechanism in mechanisms
    ]
    return draft, links


def market_signal_event_candidate(
    row: SignalTrack,
    *,
    now: datetime | None = None,
    min_confidence: float = 0.65,
) -> tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]] | None:
    if row.confidence < min_confidence:
        return None
    symbols = _symbols_for_signal_category(row.category)
    if not symbols:
        return None
    observed_at = _ensure_tz(now or datetime.now(UTC))
    event_timestamp = _ensure_tz(row.created_at or observed_at)
    mechanism = _mechanism_for_signal_type(row.signal_type)
    mechanism_zh = mechanism_label(mechanism)
    signal_zh = signal_type_label(row.signal_type)
    category_zh = category_label(row.category)
    confidence = round(min(max(row.confidence, 0.0), 1.0), 4)
    source_reliability = 0.74 if row.adversarial_passed is True else 0.62
    evidence = _compact(
        [
            f"{signal_zh} / {category_zh} 信号置信度 {confidence:.0%}。",
            f"z-score {row.z_score:.2f}。" if row.z_score is not None else "",
            f"regime: {row.regime_at_emission or row.regime}" if row.regime_at_emission or row.regime else "",
            f"outcome: {row.outcome}",
        ]
    )
    counterevidence = _compact(
        [
            "行情异常信号需要和新闻、产业数据及持仓风险交叉验证。",
            "当前入口仅进入 shadow/review，不直接改变生产阈值。",
        ]
    )
    draft = EventIntelligenceDraft(
        source_type="market",
        source_id=str(row.id),
        title=f"行情异常：{signal_zh}",
        summary=f"{category_zh}板块出现{signal_zh}，进入事件智能候选链。",
        event_type="market",
        event_timestamp=event_timestamp,
        entities=[category_zh],
        symbols=symbols,
        regions=_regions_for_symbols(symbols),
        mechanisms=[mechanism],
        evidence=evidence,
        counterevidence=counterevidence,
        confidence=confidence,
        impact_score=round(confidence * 100, 2),
        status="shadow_review",
        requires_manual_confirmation=False,
        source_reliability=source_reliability,
        freshness_score=_freshness_score(event_timestamp, observed_at),
        source_payload={
            "resolver_version": "event-intelligence-ingress-v1",
            "signal_track_id": str(row.id),
            "signal_type": row.signal_type,
            "signal_type_label": signal_zh,
            "category": row.category,
            "category_label": category_zh,
            "mechanism_label": mechanism_zh,
            "z_score": row.z_score,
            "outcome": row.outcome,
            "adversarial_passed": row.adversarial_passed,
            "production_effect": "none",
        },
    )
    links = [
        EventImpactLinkDraft(
            symbol=symbol,
            region_id=_primary_region(symbol),
            mechanism=mechanism,
            direction="watch",
            confidence=confidence,
            impact_score=round(confidence * 100, 2),
            horizon="short",
            rationale=f"{symbol} 所属{category_zh}板块出现{signal_zh}，当前先归入{mechanism_zh}机制，需结合外部事件确认方向。",
            evidence=tuple(evidence),
            counterevidence=tuple(counterevidence),
            status="shadow_review",
        )
        for symbol in symbols
    ]
    return draft, links


async def _sync_news_events(
    session: AsyncSession,
    *,
    limit: int,
    errors: list[dict[str, str]],
) -> tuple[int, int]:
    rows = list(
        (
            await session.scalars(
                select(NewsEvent).order_by(NewsEvent.published_at.desc()).limit(limit)
            )
        ).all()
    )
    created = 0
    for row in rows:
        try:
            _, _, was_created = await resolve_news_event_impacts(session, row.id)
            created += int(was_created)
        except Exception as exc:
            errors.append({"source": f"news_event:{row.id}", "error": str(exc)})
    return len(rows), created


async def _create_candidates(
    session: AsyncSession,
    candidates: list[tuple[EventIntelligenceDraft, list[EventImpactLinkDraft]]],
    *,
    actor: str,
    action: str,
    note: str,
    errors: list[dict[str, str]],
) -> tuple[int, int]:
    created = 0
    existing = 0
    for event_draft, link_drafts in candidates:
        try:
            item, links, was_created = await create_event_intelligence_from_draft(
                session,
                event_draft,
                link_drafts,
                actor=actor,
                action=action,
                note=note,
            )
            if not links:
                await record_event_intelligence_audit(
                    session,
                    event_item_id=item.id,
                    action=f"{action}.no_links",
                    actor=actor,
                    before_status=item.status,
                    after_status=item.status,
                    note="Ingress candidate had no impact links.",
                    payload={"source_type": item.source_type, "source_id": item.source_id},
                )
            if not was_created:
                await _refresh_existing_ingress_candidate(
                    session,
                    item,
                    links,
                    event_draft,
                    link_drafts,
                    actor=actor,
                    action=action,
                )
            created += int(was_created)
            existing += int(not was_created)
        except Exception as exc:
            errors.append(
                {
                    "source": f"{event_draft.source_type}:{event_draft.source_id}",
                    "error": str(exc),
                }
            )
    return created, existing


async def _refresh_existing_ingress_candidate(
    session: AsyncSession,
    item: EventIntelligenceItem,
    links: list[EventImpactLink],
    event_draft: EventIntelligenceDraft,
    link_drafts: list[EventImpactLinkDraft],
    *,
    actor: str,
    action: str,
) -> None:
    if event_draft.source_type != "market" or item.status != "shadow_review":
        return

    changed_fields: list[str] = []
    for field_name in (
        "title",
        "summary",
        "entities",
        "symbols",
        "regions",
        "mechanisms",
        "evidence",
        "counterevidence",
    ):
        next_value = getattr(event_draft, field_name)
        if isinstance(next_value, tuple):
            next_value = list(next_value)
        if getattr(item, field_name) != next_value:
            setattr(item, field_name, next_value)
            changed_fields.append(field_name)

    next_payload = {**(item.source_payload or {}), **event_draft.source_payload}
    if item.source_payload != next_payload:
        item.source_payload = next_payload
        changed_fields.append("source_payload")

    draft_by_scope = {
        (draft.symbol, draft.region_id, draft.mechanism): draft
        for draft in link_drafts
    }
    for link in links:
        if link.status != "shadow_review":
            continue
        draft = draft_by_scope.get((link.symbol, link.region_id, link.mechanism))
        if draft is None:
            continue
        for field_name in ("rationale", "evidence", "counterevidence"):
            next_value = getattr(draft, field_name)
            if isinstance(next_value, tuple):
                next_value = list(next_value)
            if getattr(link, field_name) != next_value:
                setattr(link, field_name, next_value)
                changed_fields.append(f"link.{field_name}")

    if changed_fields:
        await record_event_intelligence_audit(
            session,
            event_item_id=item.id,
            action=f"{action}.refresh_labels",
            actor=actor,
            before_status=item.status,
            after_status=item.status,
            note="Refreshed display labels for an existing market-ingress candidate.",
            payload={
                "source_type": item.source_type,
                "source_id": item.source_id,
                "changed_fields": sorted(set(changed_fields)),
                "production_effect": "none",
            },
        )


async def _load_weather_rows(session: AsyncSession, *, limit: int) -> list[IndustryData]:
    return list(
        (
            await session.scalars(
                select(IndustryData)
                .where(IndustryData.data_type.in_(WEATHER_DATA_TYPES))
                .order_by(IndustryData.timestamp.desc(), IndustryData.ingested_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def _load_market_signal_rows(session: AsyncSession, *, limit: int) -> list[SignalTrack]:
    return list(
        (
            await session.scalars(
                select(SignalTrack)
                .where(SignalTrack.confidence >= 0.65)
                .order_by(SignalTrack.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


def _weather_trigger(
    *,
    precip_anomaly: float | None,
    precip_pctile: float | None,
    precip_1h: float | None,
    temp_anomaly: float | None,
    temp_pctile: float | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    if precip_pctile is not None and precip_pctile >= 85:
        candidates.append({"kind": "rainfall_surplus", "label": f"降水分位升至 {precip_pctile:.0f}", "score": 0.82})
    if precip_anomaly is not None and precip_anomaly >= 25:
        candidates.append({"kind": "rainfall_surplus", "label": f"7日降水较基准高 {precip_anomaly:.0f}%", "score": 0.78})
    if precip_1h is not None and precip_1h >= 20:
        candidates.append({"kind": "rainfall_surplus", "label": f"1小时降水达到 {precip_1h:.1f}mm", "score": 0.7})
    if precip_pctile is not None and precip_pctile <= 15:
        candidates.append({"kind": "drought_heat", "label": f"降水分位降至 {precip_pctile:.0f}", "score": 0.76})
    if precip_anomaly is not None and precip_anomaly <= -25:
        candidates.append({"kind": "drought_heat", "label": f"7日降水较基准低 {abs(precip_anomaly):.0f}%", "score": 0.76})
    if temp_pctile is not None and temp_pctile >= 90:
        candidates.append({"kind": "drought_heat", "label": f"温度分位升至 {temp_pctile:.0f}", "score": 0.7})
    if temp_anomaly is not None and temp_anomaly >= 3:
        candidates.append({"kind": "drought_heat", "label": f"均温较基准高 {temp_anomaly:.1f}C", "score": 0.68})
    return max(candidates, key=lambda item: item["score"]) if candidates else None


def _weather_mechanisms(kind: str) -> list[str]:
    if kind == "rainfall_surplus":
        return ["weather", "supply", "logistics"]
    return ["weather", "supply"]


def _weather_confidence(
    *,
    trigger_score: float,
    has_baseline: bool,
    has_percentile: bool,
    has_current: bool,
) -> float:
    confidence = trigger_score
    if has_baseline:
        confidence += 0.05
    if has_percentile:
        confidence += 0.04
    if has_current:
        confidence += 0.03
    return round(min(confidence, 0.88), 4)


def _weather_evidence(**values: float | None) -> list[str]:
    labels = {
        "precip": "7日降水",
        "baseline_precip": "历史同期降水基准",
        "precip_anomaly": "降水距平",
        "precip_pctile": "降水历史分位",
        "precip_1h": "1小时降水",
        "temp_anomaly": "温度距平",
        "temp_pctile": "温度历史分位",
        "current_temp": "当前温度",
        "wind": "当前风速",
    }
    units = {
        "precip": "mm",
        "baseline_precip": "mm",
        "precip_anomaly": "%",
        "precip_pctile": "",
        "precip_1h": "mm",
        "temp_anomaly": "C",
        "temp_pctile": "",
        "current_temp": "C",
        "wind": "km/h",
    }
    return _compact(
        [
            f"{labels[key]} {value:.2f}{units[key]}"
            for key, value in values.items()
            if value is not None
        ]
    )


def _mechanism_for_signal_type(signal_type: str) -> str:
    text = signal_type.lower()
    if any(token in text for token in ("inventory", "stock", "warehouse")):
        return "inventory"
    if any(token in text for token in ("cost", "margin", "basis")):
        return "cost"
    if any(token in text for token in ("spread", "logistics", "freight")):
        return "logistics"
    if any(token in text for token in ("supply", "rubber_supply")):
        return "supply"
    if any(token in text for token in ("news", "weather")):
        return "weather"
    return "risk_sentiment"


def _symbols_for_signal_category(category: str) -> list[str]:
    return list(CATEGORY_SYMBOLS.get(str(category or "").strip().lower(), ()))


def _regions_for_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys(region for symbol in symbols for region in [_primary_region(symbol)] if region))


def _weather_sensitive(symbol: str) -> bool:
    profile = profile_for_symbol(symbol)
    if profile is None:
        return False
    return profile.mechanism_weights.get("weather", 0) >= 0.6


def _primary_region(symbol: str) -> str | None:
    profile = profile_for_symbol(symbol)
    if profile is None or not profile.regions:
        return None
    return profile.regions[0]


def _weather_row_region(row: IndustryData) -> str | None:
    if not row.source or ":" not in row.source:
        return None
    _, location_key = row.source.split(":", 1)
    return WEATHER_REGION_BY_LOCATION_KEY.get(location_key)


def _row_value(rows_by_type: dict[str, IndustryData], data_type: str) -> float | None:
    row = rows_by_type.get(data_type)
    return float(row.value) if row is not None else None


def _pct_change(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline <= 0:
        return None
    return round(((value - baseline) / baseline) * 100, 2)


def _root_symbol(symbol: str) -> str:
    return "".join(char for char in str(symbol).upper() if char.isalpha()) or str(symbol).upper()


def _source_families(rows: Any) -> set[str]:
    return {str(row.source).split(":", 1)[0] for row in rows if getattr(row, "source", None)}


def _industry_row_sort_key(row: IndustryData) -> tuple[datetime, datetime]:
    timestamp = _ensure_tz(row.timestamp)
    ingested_at = _ensure_tz(row.ingested_at or row.timestamp)
    return timestamp, ingested_at


def _freshness_score(event_timestamp: datetime, now: datetime) -> float:
    age_hours = max(0, (_ensure_tz(now) - _ensure_tz(event_timestamp)).total_seconds() / 3600)
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.82
    if age_hours <= 168:
        return 0.62
    return 0.45


def _ensure_tz(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _compact(values: list[str]) -> list[str]:
    return list(dict.fromkeys(text.strip()[:600] for text in values if text and text.strip()))[:8]
