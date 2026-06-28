"""Historical replay of deterministic price signals for a credible backtest.

The live ``signal_track`` table holds too few resolved + directional signals to
judge edge. Because the price-based evaluators are deterministic, we can
manufacture a large, multi-regime sample by replaying them over the backfilled
daily history (see ``akshare_history``). For each symbol we walk the main
continuous bar series day by day, feed each evaluator a trailing window
(point-in-time: only bars up to that day) and compute the forward return /
outcome from the bars that follow — producing a ``list[BacktestSignal]`` ready
for ``run_signal_backtest``.

Scope: only single-symbol price evaluators (momentum, price_gap) are replayed —
they depend solely on the bar window. Spread / basis need a paired or spot
series; news / fundamental signals can't be reconstructed historically and must
be measured live.

Slicing a once-loaded series is point-in-time correct here because backfilled
OHLC bars are not revised (one vintage per historical date); only the ``main``
continuous contract is used so a date maps to exactly one bar.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import MarketData
from app.services.backtest.signal_backtest import BacktestSignal, Horizon
from app.services.market_data.pit import _windowed_latest_statement
from app.services.signals.detector import SignalDetector
from app.services.signals.types import MarketBar, TriggerContext

REPLAYABLE_SIGNAL_TYPES: frozenset[str] = frozenset({"momentum", "price_gap"})
NATURAL_HORIZON: dict[str, Horizon] = {"momentum": 20, "price_gap": 5}

DEFAULT_LOOKBACK = 60
MIN_CONTEXT_BARS = 21
HORIZONS: tuple[Horizon, ...] = (1, 5, 20)
MAX_SERIES_BARS = 20000
MAIN_CONTRACT = "main"

SECTOR_BY_SYMBOL: dict[str, str] = {
    "RB": "ferrous",
    "HC": "ferrous",
    "I": "ferrous",
    "J": "ferrous",
    "JM": "ferrous",
    "CU": "nonferrous",
    "AL": "nonferrous",
    "ZN": "nonferrous",
    "NI": "nonferrous",
    "AU": "precious",
    "AG": "precious",
    "SC": "energy",
    "NR": "energy",
    "TA": "chemical",
    "MA": "chemical",
    "PP": "chemical",
    "BR": "chemical",
    "RU": "chemical",
    "M": "agri",
    "Y": "agri",
    "P": "agri",
}


def bars_from_rows(rows: list[MarketData]) -> list[MarketBar]:
    bars = [
        MarketBar(
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            open_interest=row.open_interest,
        )
        for row in rows
    ]
    bars.sort(key=lambda bar: bar.timestamp)
    return bars


def directional_outcome_label(direction: str | None, forward_return: float | None) -> str:
    """Mirror signals.outcomes.directional_outcome: hit when forward * sign > 0."""

    if forward_return is None:
        return "pending"
    sign = 1 if direction == "bullish" else -1 if direction == "bearish" else 0
    if sign == 0:
        return "pending"
    return "hit" if forward_return * sign > 0 else "miss"


def _forward_returns(closes: list[float], index: int) -> dict[Horizon, float | None]:
    base = closes[index]
    result: dict[Horizon, float | None] = {}
    for horizon in HORIZONS:
        ahead = index + horizon
        result[horizon] = (
            (closes[ahead] - base) / base if ahead < len(closes) and base != 0 else None
        )
    return result


async def replay_symbol_signals(
    symbol: str,
    bars: list[MarketBar],
    *,
    detector: SignalDetector | None = None,
    signal_types: frozenset[str] = REPLAYABLE_SIGNAL_TYPES,
    lookback: int = DEFAULT_LOOKBACK,
    category: str | None = None,
) -> list[BacktestSignal]:
    detector = detector or SignalDetector()
    sector = category or SECTOR_BY_SYMBOL.get(symbol, "unknown")
    requested = set(signal_types)
    closes = [bar.close for bar in bars]
    signals: list[BacktestSignal] = []

    for index in range(MIN_CONTEXT_BARS - 1, len(bars)):
        window = bars[max(0, index - lookback + 1) : index + 1]
        context = TriggerContext(
            symbol1=symbol,
            category=sector,
            timestamp=bars[index].timestamp,
            market_data=window,
        )
        results = await detector.detect(context, signal_types=requested)
        if not results:
            continue
        forward = _forward_returns(closes, index)
        for result in results:
            horizon = NATURAL_HORIZON.get(result.signal_type, 5)
            signals.append(
                BacktestSignal(
                    signal_type=result.signal_type,
                    direction=result.direction,
                    outcome=directional_outcome_label(result.direction, forward[horizon]),
                    forward_return_1d=forward[1],
                    forward_return_5d=forward[5],
                    forward_return_20d=forward[20],
                    created_at=bars[index].timestamp,
                )
            )
    return signals


def _main_series_statement(symbol: str, *, as_of: datetime | None, limit: int) -> Select:
    base = select(MarketData).where(
        MarketData.symbol == symbol,
        MarketData.contract_month == MAIN_CONTRACT,
    )
    if as_of is not None:
        base = base.where(MarketData.vintage_at <= as_of)
    # latest vintage per (symbol, main, timestamp) -> one bar per day
    return _windowed_latest_statement(
        MarketData,
        [MarketData.symbol, MarketData.contract_month, MarketData.timestamp],
        base,
        limit,
    ).order_by(MarketData.timestamp.asc())


async def load_main_series(
    session: AsyncSession,
    symbol: str,
    *,
    as_of: datetime | None = None,
    limit: int = MAX_SERIES_BARS,
) -> list[MarketBar]:
    rows = list((await session.scalars(_main_series_statement(symbol, as_of=as_of, limit=limit))).all())
    return bars_from_rows(rows)


async def replay_price_signals(
    session: AsyncSession,
    *,
    symbols: list[str] | tuple[str, ...],
    signal_types: frozenset[str] = REPLAYABLE_SIGNAL_TYPES,
    lookback: int = DEFAULT_LOOKBACK,
    as_of: datetime | None = None,
    max_series_bars: int = MAX_SERIES_BARS,
) -> list[BacktestSignal]:
    detector = SignalDetector()
    signals: list[BacktestSignal] = []
    for symbol in symbols:
        bars = await load_main_series(session, symbol, as_of=as_of, limit=max_series_bars)
        signals.extend(
            await replay_symbol_signals(
                symbol,
                bars,
                detector=detector,
                signal_types=signal_types,
                lookback=lookback,
            )
        )
    return signals
