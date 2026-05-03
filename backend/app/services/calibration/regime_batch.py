from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import MarketData
from app.models.regime_state import RegimeState
from app.services.calibration.regime_detector import RegimeDetection, detect_regime
from app.services.market_data.pit import get_market_data_pit
from app.services.signals.types import MarketBar
from app.services.signals.watchlist import get_enabled_watchlist

DEFAULT_REGIME_PERIOD = 14
MIN_REGIME_BARS = DEFAULT_REGIME_PERIOD + 2


@dataclass(frozen=True)
class SymbolRegimeDetection:
    symbol: str
    detection: RegimeDetection


@dataclass(frozen=True)
class CategoryRegimeDetection:
    category: str
    as_of_date: date
    regime: str
    adx: float
    atr_percentile: float
    trend_direction: str
    sample_size: int
    symbol_count: int


@dataclass(frozen=True)
class CategoryRegimeRecord:
    category: str
    status: str
    symbol_count: int
    regime: str | None = None
    sample_size: int = 0
    row_id: str | None = None
    reason: str | None = None

    def to_detail(self) -> dict:
        return {
            "category": self.category,
            "status": self.status,
            "symbol_count": self.symbol_count,
            "regime": self.regime,
            "sample_size": self.sample_size,
            "row_id": self.row_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RegimeBatchResult:
    categories: int
    recorded: int
    skipped: int
    as_of_date: date
    details: list[dict]


def market_row_to_bar(row: MarketData) -> MarketBar:
    return MarketBar(
        timestamp=row.timestamp,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        open_interest=row.open_interest,
    )


def aggregate_category_regime(
    *,
    category: str,
    detections: list[SymbolRegimeDetection],
    as_of_date: date,
) -> CategoryRegimeDetection | None:
    if not detections:
        return None

    weights = [max(item.detection.sample_size, 1) for item in detections]
    sample_size = sum(item.detection.sample_size for item in detections)
    return CategoryRegimeDetection(
        category=category,
        as_of_date=as_of_date,
        regime=_weighted_choice(
            [
                (item.detection.regime, weight)
                for item, weight in zip(detections, weights, strict=False)
            ]
        ),
        adx=_weighted_average(
            [
                (item.detection.adx, weight)
                for item, weight in zip(detections, weights, strict=False)
            ]
        ),
        atr_percentile=_weighted_average(
            [
                (item.detection.atr_percentile, weight)
                for item, weight in zip(detections, weights, strict=False)
            ]
        ),
        trend_direction=_weighted_choice(
            [
                (item.detection.trend_direction, weight)
                for item, weight in zip(detections, weights, strict=False)
            ]
        ),
        sample_size=sample_size,
        symbol_count=len(detections),
    )


async def detect_symbol_regime(
    session: AsyncSession,
    *,
    symbol: str,
    as_of: datetime,
    lookback_days: int = 90,
    period: int = DEFAULT_REGIME_PERIOD,
) -> SymbolRegimeDetection | None:
    start = as_of - timedelta(days=lookback_days)
    rows = await get_market_data_pit(
        session,
        symbol=symbol,
        as_of=as_of,
        start=start,
        end=as_of,
        limit=max(lookback_days * 4, period + 2),
    )
    bars = [market_row_to_bar(row) for row in rows]
    if len(bars) < period + 2:
        return None

    return SymbolRegimeDetection(
        symbol=symbol,
        detection=detect_regime(bars, period=period),
    )


async def detect_and_record_category_regime(
    session: AsyncSession,
    *,
    category: str,
    symbols: list[str],
    as_of: datetime | None = None,
    lookback_days: int = 90,
    period: int = DEFAULT_REGIME_PERIOD,
) -> CategoryRegimeRecord:
    effective_as_of = as_of or datetime.now(timezone.utc)
    unique_symbols = _unique_symbols(symbols)
    detections: list[SymbolRegimeDetection] = []

    for symbol in unique_symbols:
        detection = await detect_symbol_regime(
            session,
            symbol=symbol,
            as_of=effective_as_of,
            lookback_days=lookback_days,
            period=period,
        )
        if detection is not None:
            detections.append(detection)

    aggregate = aggregate_category_regime(
        category=category,
        detections=detections,
        as_of_date=effective_as_of.date(),
    )
    if aggregate is None:
        return CategoryRegimeRecord(
            category=category,
            status="skipped",
            symbol_count=len(unique_symbols),
            reason="insufficient_market_data",
        )

    row = await upsert_regime_state(session, aggregate)
    return CategoryRegimeRecord(
        category=category,
        status="recorded",
        symbol_count=len(unique_symbols),
        regime=aggregate.regime,
        sample_size=aggregate.sample_size,
        row_id=str(row.id),
    )


async def detect_and_record_all_regimes(
    session: AsyncSession,
    *,
    categories: list[str] | None = None,
    as_of: datetime | None = None,
    lookback_days: int = 90,
    period: int = DEFAULT_REGIME_PERIOD,
) -> RegimeBatchResult:
    effective_as_of = as_of or datetime.now(timezone.utc)
    requested_categories = set(categories or [])
    symbols_by_category = await _load_symbols_by_category(
        session,
        categories=requested_categories or None,
    )

    details: list[dict] = []
    recorded = 0
    skipped = 0
    for category, symbols in symbols_by_category.items():
        result = await detect_and_record_category_regime(
            session,
            category=category,
            symbols=symbols,
            as_of=effective_as_of,
            lookback_days=lookback_days,
            period=period,
        )
        details.append(result.to_detail())
        if result.status == "recorded":
            recorded += 1
        else:
            skipped += 1

    return RegimeBatchResult(
        categories=len(symbols_by_category),
        recorded=recorded,
        skipped=skipped,
        as_of_date=effective_as_of.date(),
        details=details,
    )


async def upsert_regime_state(
    session: AsyncSession,
    detection: CategoryRegimeDetection,
    *,
    computed_at: datetime | None = None,
) -> RegimeState:
    row = (
        await session.scalars(
            select(RegimeState)
            .where(
                RegimeState.category == detection.category,
                RegimeState.as_of_date == detection.as_of_date,
            )
            .limit(1)
        )
    ).first()
    if row is None:
        row = RegimeState(
            category=detection.category,
            as_of_date=detection.as_of_date,
            regime=detection.regime,
            adx=detection.adx,
            atr_percentile=detection.atr_percentile,
            trend_direction=detection.trend_direction,
            sample_size=detection.sample_size,
            computed_at=computed_at or datetime.now(timezone.utc),
        )
        session.add(row)
    else:
        row.regime = detection.regime
        row.adx = detection.adx
        row.atr_percentile = detection.atr_percentile
        row.trend_direction = detection.trend_direction
        row.sample_size = detection.sample_size
        row.computed_at = computed_at or datetime.now(timezone.utc)

    await session.flush()
    return row


async def _load_symbols_by_category(
    session: AsyncSession,
    *,
    categories: set[str] | None = None,
) -> dict[str, list[str]]:
    watchlist = await get_enabled_watchlist(session)
    symbols_by_category: dict[str, list[str]] = defaultdict(list)
    seen_by_category: dict[str, set[str]] = defaultdict(set)

    for entry in watchlist:
        if categories is not None and entry.category not in categories:
            continue
        for symbol in entry.symbols:
            if symbol in seen_by_category[entry.category]:
                continue
            seen_by_category[entry.category].add(symbol)
            symbols_by_category[entry.category].append(symbol)

    return dict(symbols_by_category)


def _unique_symbols(symbols: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = symbol.strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _weighted_choice(values: list[tuple[str, int]]) -> str:
    scores: dict[str, int] = defaultdict(int)
    for value, weight in values:
        scores[value] += weight
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _weighted_average(values: list[tuple[float, int]]) -> float:
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in values) / total_weight
