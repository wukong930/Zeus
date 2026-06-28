"""Long-history AKShare daily backfill for deterministic signal replay.

The near-term feed (``akshare_futures``) only carries a few hundred recent bars.
To backtest the deterministic price-based evaluators across many years and
market regimes we need a deep daily history; AKShare's ``futures_main_sina``
returns the main continuous contract over an explicit date range (≈2010→now for
most Chinese futures).

Two things make this path point-in-time correct for replay, distinct from the
near-term feed:

* ``vintage_at`` is set to each bar's **own date**, not the ingestion time, so a
  replay ``as_of=<historical day>`` can actually see the bar
  (``vintage_at <= as_of``). Using ``now()`` would hide all history.
* a dedicated ``akshare_hist:`` source-key prefix lets the backfill be idempotent
  and coexist with the near-term ``akshare_sina:`` rows as a separate vintage.

Parsing reuses the column maps and leaf helpers from ``akshare_futures`` but is
per-row resilient (a single bad bar is skipped, not fatal) and clamps OHLC so a
malformed historical row cannot violate the ``MarketDataCreate`` invariants.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

from pydantic import ValidationError

from app.schemas.common import MarketDataCreate
from app.services.data_sources import akshare_futures as af
from app.services.data_sources.types import DataSourceUnavailable

# futures_main_sina carries a "动态结算价" settle column the near-term feed lacks.
SETTLE_COLUMNS = af.SETTLE_COLUMNS + ("动态结算价", "动态结算")

HISTORY_SOURCE_PREFIX = "akshare_hist"
DEFAULT_HISTORY_START = "20100101"

# (symbol, start_date, end_date) -> frame
AkshareHistoryFetcher = Callable[[str, str, str], Any]


@dataclass(frozen=True)
class AkshareHistoryResult:
    rows: list[MarketDataCreate]
    errors: list[dict[str, str]]


def history_source_key(query_symbol: str, day: str) -> str:
    return f"{HISTORY_SOURCE_PREFIX}:{query_symbol}:{day}"


def _history_row_from_record(
    record: dict[str, Any], *, query_symbol: str
) -> MarketDataCreate | None:
    timestamp = af._parse_date(af._first(record, af.DATE_COLUMNS))
    if timestamp is None:
        return None
    close = af._float_or_none(af._first(record, af.CLOSE_COLUMNS))
    if close is None or not math.isfinite(close) or close <= 0:
        return None

    open_value = af._float_or_none(af._first(record, af.OPEN_COLUMNS)) or close
    high = af._float_or_none(af._first(record, af.HIGH_COLUMNS)) or max(open_value, close)
    low = af._float_or_none(af._first(record, af.LOW_COLUMNS)) or min(open_value, close)
    # Clamp so a single malformed bar (e.g. high < close) cannot fail the frame.
    high = max(high, open_value, low, close)
    low = min(low, open_value, close)
    # Drop bars with non-finite / non-positive prices (pandas turns gaps into NaN).
    if not all(math.isfinite(value) and value > 0 for value in (open_value, high, low)):
        return None

    settle = af._float_or_none(af._first(record, SETTLE_COLUMNS))
    base_symbol = af._base_symbol(query_symbol)
    try:
        return MarketDataCreate(
            source_key=history_source_key(query_symbol, timestamp.date().isoformat()),
            market="CN",
            exchange=af.EXCHANGE_BY_SYMBOL.get(base_symbol, "UNKNOWN"),
            commodity=af.COMMODITY_NAMES.get(base_symbol, base_symbol),
            symbol=base_symbol,
            contract_month=af._contract_month(query_symbol),
            timestamp=timestamp,
            open=open_value,
            high=high,
            low=low,
            close=close,
            settle=settle if settle is not None and settle > 0 else None,
            volume=af._float_or_none(af._first(record, af.VOLUME_COLUMNS)) or 0.0,
            open_interest=af._float_or_none(af._first(record, af.OPEN_INTEREST_COLUMNS)),
            currency="CNY",
            timezone="Asia/Shanghai",
            vintage_at=timestamp,
        )
    except ValidationError:
        return None


def history_rows_from_frame(frame: Any, *, query_symbol: str) -> list[MarketDataCreate]:
    if frame is None or getattr(frame, "empty", False):
        return []
    af._validate_frame_columns(frame, query_symbol=query_symbol)
    rows: list[MarketDataCreate] = []
    for record in frame.to_dict("records"):
        row = _history_row_from_record(record, query_symbol=query_symbol)
        if row is not None:
            rows.append(row)
    return rows


def _default_history_fetcher() -> AkshareHistoryFetcher:
    try:
        akshare = import_module("akshare")
    except ImportError as exc:
        raise DataSourceUnavailable("AKShare is not installed in the backend image.") from exc

    def fetch(symbol: str, start_date: str, end_date: str) -> Any:
        return akshare.futures_main_sina(symbol=symbol, start_date=start_date, end_date=end_date)

    return fetch


async def collect_akshare_history(
    *,
    symbols: list[str] | tuple[str, ...] = af.DEFAULT_AKSHARE_SYMBOLS,
    start_date: str = DEFAULT_HISTORY_START,
    end_date: str,
    fetcher: AkshareHistoryFetcher | None = None,
) -> AkshareHistoryResult:
    fetch = fetcher or _default_history_fetcher()
    rows: list[MarketDataCreate] = []
    errors: list[dict[str, str]] = []

    for symbol in symbols:
        try:
            frame = await asyncio.to_thread(fetch, symbol, start_date, end_date)
            rows.extend(history_rows_from_frame(frame, query_symbol=symbol))
        except Exception as exc:
            errors.append({"source": f"{HISTORY_SOURCE_PREFIX}:{symbol}", "error": str(exc)})

    return AkshareHistoryResult(rows=rows, errors=errors)
