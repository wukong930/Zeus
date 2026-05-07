from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import IndustryDataCreate

UTC = ZoneInfo("UTC")
REQUIRED_FRED_OBSERVATION_FIELDS = {"date", "value"}


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    symbol: str
    data_type: str
    unit: str


DEFAULT_FRED_SERIES: tuple[FredSeries, ...] = (
    FredSeries("DCOILWTICO", "SC", "macro_wti_usd_bbl", "USD/bbl"),
    FredSeries("DCOILBRENTEU", "SC", "macro_brent_usd_bbl", "USD/bbl"),
    FredSeries("DHHNGSP", "SC", "macro_henry_hub", "USD/MMBtu"),
    FredSeries("DTWEXBGS", "MACRO", "macro_usd_index", "index"),
    FredSeries("DGS10", "MACRO", "macro_us10y_yield", "pct"),
)


async def collect_fred_indicators(
    *,
    api_key: str,
    base_url: str,
    series: tuple[FredSeries, ...] = DEFAULT_FRED_SERIES,
    timeout: float = 15.0,
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
                f"{base_url.rstrip('/')}/series/observations",
                params={
                    "series_id": item.series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 10,
                },
            )
            response.raise_for_status()
            row = row_from_fred_payload(item, response.json())
            if row is not None:
                rows.append(row)
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


def row_from_fred_payload(
    series: FredSeries,
    payload: dict[str, Any],
) -> IndustryDataCreate | None:
    observations = payload.get("observations")
    if not isinstance(observations, list):
        message = payload.get("error_message") or payload.get("message")
        raise RuntimeError(str(message or "FRED payload missing observations"))
    if observations and not any(_has_observation_shape(observation) for observation in observations):
        raise RuntimeError("FRED payload missing observation date/value")
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        value = observation.get("value")
        if value in {None, "."}:
            continue
        try:
            numeric = float(value)
            timestamp = datetime.fromisoformat(str(observation["date"])).replace(tzinfo=UTC)
        except (KeyError, TypeError, ValueError):
            continue
        return IndustryDataCreate(
            source_key=f"fred:{series.series_id}:{timestamp.date().isoformat()}",
            symbol=series.symbol,
            data_type=series.data_type,
            value=numeric,
            unit=series.unit,
            source="fred",
            timestamp=timestamp,
        )
    return None


def _has_observation_shape(observation: Any) -> bool:
    return isinstance(observation, dict) and REQUIRED_FRED_OBSERVATION_FIELDS <= observation.keys()
