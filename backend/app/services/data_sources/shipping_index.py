from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import IndustryDataCreate

UTC = ZoneInfo("UTC")
DEFAULT_SHIPPING_INDEX_SYMBOLS: tuple[str, ...] = ("FREIGHT", "RU", "NR", "BR", "SC", "I")
MAX_SHIPPING_INDEX_SYMBOLS = 50
DATE_FIELDS = ("date", "timestamp", "period", "week", "time", "index_date", "as_of")
VALUE_FIELDS = ("value", "close", "index_value", "price", "rate", "freight_rate")
LABEL_FIELDS = (
    "data_type",
    "series",
    "series_id",
    "index",
    "index_name",
    "name",
    "label",
    "route",
    "code",
    "id",
)
UNIT_FIELDS = ("unit", "units", "uom")
RECORD_LIST_FIELDS = ("data", "rows", "items", "observations", "records", "result")


@dataclass(frozen=True)
class ShippingIndexSpec:
    key: str
    aliases: tuple[str, ...]
    data_type: str
    unit: str


DEFAULT_SHIPPING_INDEX_SPECS: tuple[ShippingIndexSpec, ...] = (
    ShippingIndexSpec(
        key="ccfi",
        aliases=(
            "ccfi",
            "china containerized freight index",
            "china export containerized freight index",
            "中国出口集装箱运价指数",
        ),
        data_type="shipping_ccfi_index",
        unit="index",
    ),
    ShippingIndexSpec(
        key="scfi",
        aliases=("scfi", "shanghai containerized freight index", "上海出口集装箱运价指数"),
        data_type="shipping_scfi_index",
        unit="index",
    ),
    ShippingIndexSpec(
        key="wci",
        aliases=("wci", "world container index", "drewry"),
        data_type="shipping_wci_usd_feu",
        unit="USD/FEU",
    ),
    ShippingIndexSpec(
        key="fbx",
        aliases=("fbx", "freightos baltic", "freightos global", "freightos"),
        data_type="shipping_fbx_usd_feu",
        unit="USD/FEU",
    ),
    ShippingIndexSpec(
        key="bdi",
        aliases=("bdi", "baltic dry index", "baltic dry"),
        data_type="shipping_bdi_index",
        unit="index",
    ),
    ShippingIndexSpec(
        key="cdfi",
        aliases=("cdfi", "china coastal bulk freight index", "中国沿海散货运价指数"),
        data_type="shipping_cdfi_index",
        unit="index",
    ),
)


async def collect_shipping_index_indicators(
    *,
    url: str,
    symbols: tuple[str, ...] = DEFAULT_SHIPPING_INDEX_SYMBOLS,
    specs: tuple[ShippingIndexSpec, ...] = DEFAULT_SHIPPING_INDEX_SPECS,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    if not url.strip():
        return []

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await active_client.get(url)
        response.raise_for_status()
        return rows_from_shipping_index_payload(response.text, symbols=symbols, specs=specs)
    finally:
        if owns_client:
            await active_client.aclose()


def parse_shipping_index_symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_SHIPPING_INDEX_SYMBOLS
    symbols = tuple(dict.fromkeys(part.strip().upper() for part in value.split(",") if part.strip()))
    if len(symbols) > MAX_SHIPPING_INDEX_SYMBOLS:
        raise ValueError(f"Shipping index symbols can contain at most {MAX_SHIPPING_INDEX_SYMBOLS} entries")
    oversized = [symbol for symbol in symbols if len(symbol) > 32]
    if oversized:
        raise ValueError("Shipping index symbols can be at most 32 characters")
    return symbols or DEFAULT_SHIPPING_INDEX_SYMBOLS


def rows_from_shipping_index_payload(
    payload: Any,
    *,
    symbols: tuple[str, ...] = DEFAULT_SHIPPING_INDEX_SYMBOLS,
    specs: tuple[ShippingIndexSpec, ...] = DEFAULT_SHIPPING_INDEX_SPECS,
) -> list[IndustryDataCreate]:
    records = _records_from_payload(payload)
    if not records:
        return []
    if not any(_has_candidate_shape(record) for record in records):
        raise RuntimeError("Shipping index payload missing date/value/series fields")

    target_symbols = parse_shipping_index_symbols(",".join(symbols))
    rows: list[IndustryDataCreate] = []
    for record in records:
        spec = _spec_for_record(record, specs)
        if spec is None:
            continue
        timestamp = _parse_timestamp(_first(record, DATE_FIELDS))
        value = _float_or_none(_first(record, VALUE_FIELDS))
        if timestamp is None or value is None:
            continue
        unit = _clean_unit(_first(record, UNIT_FIELDS), spec.unit)
        for symbol in target_symbols:
            rows.append(
                IndustryDataCreate(
                    source_key=(
                        f"shipping_index:{spec.key}:{symbol}:"
                        f"{spec.data_type}:{timestamp.date().isoformat()}"
                    ),
                    symbol=symbol,
                    data_type=spec.data_type,
                    value=value,
                    unit=unit,
                    source=f"shipping_index:{spec.key}",
                    timestamp=timestamp,
                )
            )
    return rows


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    parsed = _parse_payload(payload)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return []
    for field in RECORD_LIST_FIELDS:
        value = parsed.get(field)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records_from_payload(value)
            if nested:
                return nested
    response = parsed.get("response")
    if isinstance(response, dict):
        nested = _records_from_payload(response)
        if nested:
            return nested
    return [parsed] if _has_candidate_shape(parsed) else []


def _parse_payload(payload: Any) -> Any:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if not isinstance(payload, str):
        return payload
    text = payload.strip()
    if not text:
        return []
    if text.startswith(("{", "[")):
        return json.loads(text)

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        return []
    return list(reader)


def _has_candidate_shape(record: dict[str, Any]) -> bool:
    normalized = _normalized_record(record)
    has_date = any(field in normalized for field in DATE_FIELDS)
    has_value = any(field in normalized for field in VALUE_FIELDS)
    has_label = any(field in normalized for field in LABEL_FIELDS)
    return has_date or has_value or has_label


def _spec_for_record(
    record: dict[str, Any],
    specs: tuple[ShippingIndexSpec, ...],
) -> ShippingIndexSpec | None:
    data_type = str(_first(record, ("data_type",)) or "").strip().lower()
    for spec in specs:
        if data_type == spec.data_type:
            return spec

    label = " ".join(
        str(value).strip().lower()
        for value in (_first(record, (field,)) for field in LABEL_FIELDS)
        if value not in {None, ""}
    )
    if not label:
        return None
    for spec in specs:
        if any(alias.lower() in label for alias in spec.aliases):
            return spec
    return None


def _first(record: dict[str, Any], fields: tuple[str, ...]) -> Any:
    normalized = _normalized_record(record)
    for field in fields:
        if field in normalized:
            return normalized[field]
    return None


def _normalized_record(record: dict[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in record.items()}


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for parser in (
        lambda raw: datetime.fromisoformat(raw),
        lambda raw: datetime.strptime(raw, "%Y%m%d"),
        lambda raw: datetime.strptime(raw, "%Y-%m"),
        lambda raw: datetime.strptime(raw, "%d-%b-%y"),
        lambda raw: datetime.strptime(raw, "%d-%b-%Y"),
    ):
        try:
            parsed = parser(text)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _clean_unit(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    unit = str(value).strip()
    if not unit or len(unit) > 20:
        return fallback
    return unit
