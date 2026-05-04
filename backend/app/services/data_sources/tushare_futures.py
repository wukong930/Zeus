from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import MarketDataCreate
from app.services.data_sources.akshare_futures import COMMODITY_NAMES, EXCHANGE_BY_SYMBOL

CHINA_TZ = ZoneInfo("Asia/Shanghai")

DEFAULT_TUSHARE_EXCHANGES: tuple[str, ...] = ("SHFE", "DCE", "CZCE", "INE")
DEFAULT_TUSHARE_SYMBOLS: tuple[str, ...] = (
    "RB",
    "HC",
    "I",
    "J",
    "JM",
    "RU",
    "NR",
    "BR",
    "SC",
    "TA",
    "MA",
    "PP",
    "CU",
    "AL",
    "ZN",
    "NI",
    "M",
    "Y",
    "P",
    "AU",
    "AG",
)

TUSHARE_FIELDS = "ts_code,trade_date,open,high,low,close,settle,vol,oi"
TUSHARE_EXCHANGE_SUFFIXES = {
    "SHFE": "SHF",
    "DCE": "DCE",
    "CZCE": "CZC",
    "INE": "INE",
    "GFEX": "GFE",
}


@dataclass(frozen=True)
class TushareFetchResult:
    rows: list[MarketDataCreate]
    errors: list[dict[str, str]]


async def collect_tushare_market_data(
    *,
    token: str,
    base_url: str,
    exchanges: tuple[str, ...] = DEFAULT_TUSHARE_EXCHANGES,
    symbols: tuple[str, ...] = DEFAULT_TUSHARE_SYMBOLS,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> TushareFetchResult:
    if not token.strip():
        return TushareFetchResult(rows=[], errors=[])

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    rows: list[MarketDataCreate] = []
    errors: list[dict[str, str]] = []
    try:
        for exchange in exchanges:
            try:
                response = await active_client.post(
                    base_url,
                    json={
                        "api_name": "fut_daily",
                        "token": token,
                        "params": {"exchange": exchange},
                        "fields": TUSHARE_FIELDS,
                    },
                )
                response.raise_for_status()
                rows.extend(
                    rows_from_tushare_payload(
                        response.json(),
                        exchange=exchange,
                        symbols=symbols,
                    )
                )
            except Exception as exc:
                errors.append({"source": f"tushare:{exchange}", "error": str(exc)})
        return TushareFetchResult(rows=dedupe_active_contracts(rows), errors=errors)
    finally:
        if owns_client:
            await active_client.aclose()


def rows_from_tushare_payload(
    payload: dict[str, Any],
    *,
    exchange: str,
    symbols: tuple[str, ...] = DEFAULT_TUSHARE_SYMBOLS,
) -> list[MarketDataCreate]:
    code = payload.get("code")
    if code not in {0, "0", None}:
        message = payload.get("msg") or payload.get("message") or "Tushare API error"
        raise RuntimeError(str(message))

    data = payload.get("data")
    fields = data.get("fields") if isinstance(data, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(fields, list) or not isinstance(items, list):
        return []

    records = [dict(zip(fields, item, strict=False)) for item in items if isinstance(item, list)]
    rows: list[MarketDataCreate] = []
    for record in records:
        row = _row_from_record(record, exchange=exchange, symbols=symbols)
        if row is not None:
            rows.append(row)
    return rows


def dedupe_active_contracts(rows: list[MarketDataCreate]) -> list[MarketDataCreate]:
    best: dict[str, MarketDataCreate] = {}
    for row in rows:
        current = best.get(row.symbol)
        if current is None or _active_sort_key(row) > _active_sort_key(current):
            best[row.symbol] = row
    return sorted(best.values(), key=lambda item: item.symbol)


def parse_csv_tuple(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    return parsed or default


def _row_from_record(
    record: dict[str, Any],
    *,
    exchange: str,
    symbols: tuple[str, ...],
) -> MarketDataCreate | None:
    ts_code = str(record.get("ts_code") or "").upper()
    parsed = _parse_ts_code(ts_code, symbols=symbols)
    if parsed is None:
        return None
    base_symbol, contract_month = parsed
    timestamp = _parse_trade_date(record.get("trade_date"))
    close = _float_or_none(record.get("close"))
    if timestamp is None or close is None:
        return None

    open_value = _float_or_none(record.get("open")) or close
    high = _float_or_none(record.get("high")) or max(open_value, close)
    low = _float_or_none(record.get("low")) or min(open_value, close)
    exchange_name = _normalize_exchange(exchange, ts_code, base_symbol)
    return MarketDataCreate(
        source_key=f"tushare:fut_daily:{ts_code}:{timestamp.date().isoformat()}",
        market="CN",
        exchange=exchange_name,
        commodity=COMMODITY_NAMES.get(base_symbol, base_symbol),
        symbol=base_symbol,
        contract_month=contract_month,
        timestamp=timestamp,
        open=open_value,
        high=high,
        low=low,
        close=close,
        settle=_float_or_none(record.get("settle")),
        volume=_float_or_none(record.get("vol")) or 0.0,
        open_interest=_float_or_none(record.get("oi")),
        currency="CNY",
        timezone="Asia/Shanghai",
    )


def _parse_ts_code(ts_code: str, *, symbols: tuple[str, ...]) -> tuple[str, str] | None:
    code = ts_code.split(".", maxsplit=1)[0]
    for symbol in sorted(symbols, key=len, reverse=True):
        match = re.match(rf"^{re.escape(symbol)}(\d+)$", code)
        if match:
            return symbol, match.group(1)
    return None


def _parse_trade_date(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        return datetime.strptime(str(value), "%Y%m%d").replace(tzinfo=CHINA_TZ)
    except ValueError:
        return None


def _normalize_exchange(exchange: str, ts_code: str, base_symbol: str) -> str:
    suffix = ts_code.split(".")[-1] if "." in ts_code else ""
    for canonical, tushare_suffix in TUSHARE_EXCHANGE_SUFFIXES.items():
        if suffix == tushare_suffix:
            return canonical
    return exchange or EXCHANGE_BY_SYMBOL.get(base_symbol, "UNKNOWN")


def _active_sort_key(row: MarketDataCreate) -> tuple[datetime, float, float]:
    return (row.timestamp, row.open_interest or 0.0, row.volume)


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
