from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import IndustryDataCreate

UTC = ZoneInfo("UTC")
REQUIRED_EIA_DATA_FIELDS = {"period", "series", "value"}


@dataclass(frozen=True)
class EiaSeries:
    route: str
    series_id: str
    symbol: str
    data_type: str
    unit: str


DEFAULT_EIA_SERIES: tuple[EiaSeries, ...] = (
    EiaSeries(
        "petroleum/stoc/wstk",
        "WCESTUS1",
        "SC",
        "eia_crude_stocks_ex_spr",
        "MBBL",
    ),
    EiaSeries("petroleum/stoc/wstk", "WGTSTUS1", "SC", "eia_gasoline_stocks", "MBBL"),
    EiaSeries("petroleum/stoc/wstk", "WDISTUS1", "SC", "eia_distillate_stocks", "MBBL"),
    EiaSeries(
        "petroleum/pnp/wiup",
        "WPULEUS3",
        "SC",
        "eia_refinery_utilization",
        "pct",
    ),
    EiaSeries(
        "petroleum/pnp/wiup",
        "WCRRIUS2",
        "SC",
        "eia_crude_refinery_input",
        "MBBL/D",
    ),
)


async def collect_eia_indicators(
    *,
    api_key: str,
    base_url: str,
    series: tuple[EiaSeries, ...] = DEFAULT_EIA_SERIES,
    timeout: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    if not api_key.strip():
        return []

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        for item in series:
            response = await active_client.get(
                f"{base_url.rstrip('/')}/v2/{item.route.strip('/')}/data/",
                params={
                    "api_key": api_key,
                    "frequency": "weekly",
                    "data[0]": "value",
                    "facets[series][]": item.series_id,
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "offset": 0,
                    "length": 5,
                },
            )
            response.raise_for_status()
            row = row_from_eia_payload(item, response.json())
            if row is not None:
                rows.append(row)
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


def row_from_eia_payload(series: EiaSeries, payload: dict[str, Any]) -> IndustryDataCreate | None:
    response = payload.get("response")
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list):
        message = payload.get("error") or payload.get("message")
        if isinstance(response, dict):
            message = message or response.get("error") or response.get("message")
        raise RuntimeError(str(message or "EIA payload missing response.data"))
    if data and not any(_has_eia_data_shape(item) for item in data):
        raise RuntimeError("EIA payload missing data period/series/value")

    for item in data:
        if not isinstance(item, dict):
            continue
        if str(item.get("series") or "") != series.series_id:
            continue
        value = _float_or_none(item.get("value"))
        period = item.get("period")
        if value is None or not period:
            continue
        try:
            timestamp = datetime.fromisoformat(str(period)).replace(tzinfo=UTC)
        except ValueError:
            continue
        return IndustryDataCreate(
            source_key=f"eia:{series.series_id}:{timestamp.date().isoformat()}",
            symbol=series.symbol,
            data_type=series.data_type,
            value=value,
            unit=str(item.get("units") or series.unit),
            source="eia",
            timestamp=timestamp,
        )
    return None


def _has_eia_data_shape(item: Any) -> bool:
    return isinstance(item, dict) and REQUIRED_EIA_DATA_FIELDS <= item.keys()


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
