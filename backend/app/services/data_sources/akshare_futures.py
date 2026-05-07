from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.schemas.common import MarketDataCreate
from app.services.data_sources.types import DataSourceUnavailable

CHINA_TZ = ZoneInfo("Asia/Shanghai")

DEFAULT_AKSHARE_SYMBOLS: tuple[str, ...] = (
    "RB0",
    "HC0",
    "I0",
    "J0",
    "JM0",
    "RU0",
    "NR0",
    "BR0",
    "SC0",
    "TA0",
    "MA0",
    "PP0",
    "CU0",
    "AL0",
    "ZN0",
    "NI0",
    "M0",
    "Y0",
    "P0",
    "AU0",
    "AG0",
)

COMMODITY_NAMES = {
    "RB": "螺纹钢",
    "HC": "热卷",
    "I": "铁矿石",
    "J": "焦炭",
    "JM": "焦煤",
    "RU": "天然橡胶",
    "NR": "20号胶",
    "BR": "顺丁橡胶",
    "SC": "原油",
    "TA": "PTA",
    "MA": "甲醇",
    "PP": "聚丙烯",
    "CU": "铜",
    "AL": "铝",
    "ZN": "锌",
    "NI": "镍",
    "M": "豆粕",
    "Y": "豆油",
    "P": "棕榈油",
    "AU": "黄金",
    "AG": "白银",
}

EXCHANGE_BY_SYMBOL = {
    "RB": "SHFE",
    "HC": "SHFE",
    "CU": "SHFE",
    "AL": "SHFE",
    "ZN": "SHFE",
    "NI": "SHFE",
    "AU": "SHFE",
    "AG": "SHFE",
    "RU": "SHFE",
    "NR": "INE",
    "SC": "INE",
    "I": "DCE",
    "J": "DCE",
    "JM": "DCE",
    "PP": "DCE",
    "M": "DCE",
    "Y": "DCE",
    "P": "DCE",
    "TA": "CZCE",
    "MA": "CZCE",
    "BR": "SHFE",
}

DATE_COLUMNS = ("date", "日期", "trade_date", "交易日期")
OPEN_COLUMNS = ("open", "开盘", "开盘价")
HIGH_COLUMNS = ("high", "最高", "最高价")
LOW_COLUMNS = ("low", "最低", "最低价")
CLOSE_COLUMNS = ("close", "收盘", "收盘价")
SETTLE_COLUMNS = ("settle", "结算", "结算价")
VOLUME_COLUMNS = ("volume", "成交量", "vol")
OPEN_INTEREST_COLUMNS = ("hold", "持仓量", "open_interest", "oi")
REQUIRED_FRAME_COLUMN_GROUPS = {
    "date": DATE_COLUMNS,
    "close": CLOSE_COLUMNS,
}

AkshareFetcher = Callable[[str], Any]


@dataclass(frozen=True)
class AkshareFetchResult:
    rows: list[MarketDataCreate]
    errors: list[dict[str, str]]


async def collect_akshare_market_data(
    *,
    symbols: list[str] | tuple[str, ...] = DEFAULT_AKSHARE_SYMBOLS,
    limit: int = 80,
    fetcher: AkshareFetcher | None = None,
) -> AkshareFetchResult:
    fetch = fetcher or _default_fetcher()
    rows: list[MarketDataCreate] = []
    errors: list[dict[str, str]] = []

    for query_symbol in symbols:
        try:
            frame = await asyncio.to_thread(fetch, query_symbol)
            rows.extend(_rows_from_frame(frame, query_symbol=query_symbol, limit=limit))
        except Exception as exc:
            errors.append({"source": f"akshare:{query_symbol}", "error": str(exc)})

    return AkshareFetchResult(rows=rows, errors=errors)


def _default_fetcher() -> AkshareFetcher:
    try:
        akshare = import_module("akshare")
    except ImportError as exc:
        raise DataSourceUnavailable("AKShare is not installed in the backend image.") from exc
    return akshare.futures_zh_daily_sina


def _rows_from_frame(frame: Any, *, query_symbol: str, limit: int) -> list[MarketDataCreate]:
    if frame is None or getattr(frame, "empty", False):
        return []

    _validate_frame_columns(frame, query_symbol=query_symbol)
    records = frame.tail(max(1, limit)).to_dict("records")
    base_symbol = _base_symbol(query_symbol)
    contract_month = _contract_month(query_symbol)
    rows: list[MarketDataCreate] = []

    for record in records:
        timestamp = _parse_date(_first(record, DATE_COLUMNS))
        if timestamp is None:
            continue
        close = _float_or_none(_first(record, CLOSE_COLUMNS))
        if close is None:
            continue
        open_value = _float_or_none(_first(record, OPEN_COLUMNS)) or close
        high = _float_or_none(_first(record, HIGH_COLUMNS)) or max(open_value, close)
        low = _float_or_none(_first(record, LOW_COLUMNS)) or min(open_value, close)
        settle = _float_or_none(_first(record, SETTLE_COLUMNS))
        rows.append(
            MarketDataCreate(
                source_key=f"akshare_sina:{query_symbol}:{timestamp.date().isoformat()}",
                market="CN",
                exchange=EXCHANGE_BY_SYMBOL.get(base_symbol, "UNKNOWN"),
                commodity=COMMODITY_NAMES.get(base_symbol, base_symbol),
                symbol=base_symbol,
                contract_month=contract_month,
                timestamp=timestamp,
                open=open_value,
                high=high,
                low=low,
                close=close,
                settle=settle,
                volume=_float_or_none(_first(record, VOLUME_COLUMNS)) or 0.0,
                open_interest=_float_or_none(_first(record, OPEN_INTEREST_COLUMNS)),
                currency="CNY",
                timezone="Asia/Shanghai",
            )
        )
    return rows


def parse_akshare_symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_AKSHARE_SYMBOLS
    symbols = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    return symbols or DEFAULT_AKSHARE_SYMBOLS


def _first(record: dict[str, Any], columns: tuple[str, ...]) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in record.items()}
    for column in columns:
        key = column.lower()
        if key in normalized:
            return normalized[key]
    return None


def _validate_frame_columns(frame: Any, *, query_symbol: str) -> None:
    normalized_columns = {str(column).strip().lower() for column in getattr(frame, "columns", [])}
    missing = [
        label
        for label, candidates in REQUIRED_FRAME_COLUMN_GROUPS.items()
        if not any(candidate.lower() in normalized_columns for candidate in candidates)
    ]
    if missing:
        raise RuntimeError(f"AKShare payload for {query_symbol} missing columns: {', '.join(missing)}")


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("/", "-"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def _base_symbol(query_symbol: str) -> str:
    return re.sub(r"\d+$", "", query_symbol.upper())


def _contract_month(query_symbol: str) -> str:
    digits = "".join(re.findall(r"\d+", query_symbol))
    return "main" if digits in {"", "0"} else digits[-4:]
