from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib import import_module
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.schemas.common import IndustryDataCreate
from app.services.data_sources.types import DataSourceUnavailable

CHINA_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_RUBBER_SPOT_SYMBOLS: tuple[str, ...] = ("RU", "NR", "BR")
DEFAULT_RUBBER_SPOT_HISTORY_DAYS = 7
MAX_RUBBER_SPOT_SYMBOLS = 20
MAX_RUBBER_SPOT_HISTORY_DAYS = 30
RUBBER_SPOT_SOURCE = "akshare_100ppi"
REQUIRED_FRAME_COLUMN_GROUPS: dict[str, tuple[str, ...]] = {
    "date": ("date", "日期"),
    "symbol": ("symbol", "var", "商品品种", "品种"),
    "spot_price": ("spot_price", "sp", "现货价格"),
}

RubberSpotFetcher = Callable[[str, str, list[str]], Any]


@dataclass(frozen=True)
class RubberSpotFetchResult:
    rows: list[IndustryDataCreate]
    errors: list[dict[str, str]]


async def collect_rubber_spot_indicators(
    *,
    symbols: tuple[str, ...] = DEFAULT_RUBBER_SPOT_SYMBOLS,
    history_days: int = DEFAULT_RUBBER_SPOT_HISTORY_DAYS,
    today: date | None = None,
    fetcher: RubberSpotFetcher | None = None,
) -> RubberSpotFetchResult:
    normalized_symbols = parse_rubber_spot_symbols(",".join(symbols))
    bounded_history_days = min(max(1, int(history_days)), MAX_RUBBER_SPOT_HISTORY_DAYS)
    end_day = today or date.today()
    start_day = end_day - timedelta(days=bounded_history_days - 1)
    fetch = fetcher or _default_fetcher()

    try:
        frame = await asyncio.to_thread(
            fetch,
            start_day.strftime("%Y%m%d"),
            end_day.strftime("%Y%m%d"),
            list(normalized_symbols),
        )
        rows = rows_from_rubber_spot_frame(frame, symbols=normalized_symbols)
        return RubberSpotFetchResult(rows=rows, errors=[])
    except Exception as exc:
        return RubberSpotFetchResult(
            rows=[],
            errors=[{"source": "rubber_spot", "error": str(exc)}],
        )


def parse_rubber_spot_symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_RUBBER_SPOT_SYMBOLS
    symbols = tuple(
        dict.fromkeys(part.strip().upper() for part in value.split(",") if part.strip())
    )
    if len(symbols) > MAX_RUBBER_SPOT_SYMBOLS:
        raise ValueError(f"Rubber spot symbols can contain at most {MAX_RUBBER_SPOT_SYMBOLS} entries")
    oversized = [symbol for symbol in symbols if len(symbol) > 12]
    if oversized:
        raise ValueError("Rubber spot symbols can be at most 12 characters")
    return symbols or DEFAULT_RUBBER_SPOT_SYMBOLS


def rows_from_rubber_spot_frame(
    frame: Any,
    *,
    symbols: tuple[str, ...] = DEFAULT_RUBBER_SPOT_SYMBOLS,
) -> list[IndustryDataCreate]:
    if frame is None or getattr(frame, "empty", False):
        return []

    _validate_frame_columns(frame)
    records = frame.to_dict("records")
    rows: list[IndustryDataCreate] = []
    allowed_symbols = {symbol.upper() for symbol in symbols}

    for record in records:
        symbol = _symbol(record)
        if not symbol or symbol not in allowed_symbols:
            continue
        timestamp = _parse_date(_first(record, ("date", "日期")))
        if timestamp is None:
            continue
        rows.extend(_rows_from_record(symbol, timestamp, record))

    return rows


def _rows_from_record(
    symbol: str,
    timestamp: datetime,
    record: dict[str, Any],
) -> list[IndustryDataCreate]:
    specs = (
        (
            "rubber_spot_price_cny_t",
            ("spot_price", "sp", "现货价格"),
            "CNY/t",
        ),
        (
            "rubber_near_basis_cny_t",
            ("near_basis", "临近交割合约相对现货的基差"),
            "CNY/t",
        ),
        (
            "rubber_dom_basis_cny_t",
            ("dom_basis", "主力合约相对现货的基差"),
            "CNY/t",
        ),
        (
            "rubber_near_basis_rate",
            ("near_basis_rate", "临近交割合约相对现货的基差率"),
            "ratio",
        ),
        (
            "rubber_dom_basis_rate",
            ("dom_basis_rate", "主力合约相对现货的基差率"),
            "ratio",
        ),
    )
    rows: list[IndustryDataCreate] = []
    for data_type, columns, unit in specs:
        value = _float_or_none(_first(record, columns))
        if value is None:
            continue
        rows.append(
            IndustryDataCreate(
                source_key=(
                    f"{RUBBER_SPOT_SOURCE}:rubber_spot:{symbol}:"
                    f"{data_type}:{timestamp.date().isoformat()}"
                ),
                symbol=symbol,
                data_type=data_type,
                value=value,
                unit=unit,
                source=f"{RUBBER_SPOT_SOURCE}:{symbol}",
                timestamp=timestamp,
            )
        )
    return rows


def _default_fetcher() -> RubberSpotFetcher:
    try:
        akshare = import_module("akshare")
    except ImportError as exc:
        raise DataSourceUnavailable("AKShare is not installed in the backend image.") from exc
    return akshare.futures_spot_price_daily


def _validate_frame_columns(frame: Any) -> None:
    normalized_columns = {str(column).strip().lower() for column in getattr(frame, "columns", [])}
    missing = [
        label
        for label, candidates in REQUIRED_FRAME_COLUMN_GROUPS.items()
        if not any(candidate.lower() in normalized_columns for candidate in candidates)
    ]
    if missing:
        raise RuntimeError(f"Rubber spot payload missing columns: {', '.join(missing)}")


def _symbol(record: dict[str, Any]) -> str | None:
    value = _first(record, ("symbol", "var", "商品品种", "品种"))
    if value is None:
        return None
    return str(value).strip().upper()


def _first(record: dict[str, Any], columns: tuple[str, ...]) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in record.items()}
    for column in columns:
        key = column.lower()
        if key in normalized:
            return normalized[key]
    return None


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(CHINA_TZ)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=CHINA_TZ)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=CHINA_TZ)
        except ValueError:
            continue
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
