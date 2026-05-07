from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import IndustryDataCreate

OPEN_METEO_FORECAST_API = "https://api.open-meteo.com/v1/forecast"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
REQUIRED_DAILY_FIELDS = (
    "time",
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
)


@dataclass(frozen=True)
class WeatherLocation:
    key: str
    label: str
    symbol: str
    latitude: float
    longitude: float


DEFAULT_WEATHER_LOCATIONS: tuple[WeatherLocation, ...] = (
    WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0084, 100.4767),
    WeatherLocation("songkhla", "Songkhla", "NR", 7.1898, 100.5951),
    WeatherLocation("hainan", "Hainan", "RU", 19.5664, 109.9497),
    WeatherLocation("yunnan", "Yunnan", "RU", 22.0094, 100.7974),
    WeatherLocation("qingdao", "Qingdao", "RU", 36.0671, 120.3826),
)


async def collect_open_meteo_weather(
    *,
    locations: tuple[WeatherLocation, ...] = DEFAULT_WEATHER_LOCATIONS,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        for location in locations:
            response = await active_client.get(
                OPEN_METEO_FORECAST_API,
                params={
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
                    "forecast_days": 7,
                    "timezone": "Asia/Shanghai",
                },
            )
            response.raise_for_status()
            rows.extend(rows_from_weather_payload(location, response.json()))
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


def rows_from_weather_payload(
    location: WeatherLocation,
    payload: dict[str, Any],
) -> list[IndustryDataCreate]:
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise RuntimeError("Open-Meteo payload missing daily data")

    missing_fields = [field for field in REQUIRED_DAILY_FIELDS if field not in daily]
    if missing_fields:
        raise RuntimeError(f"Open-Meteo payload missing daily fields: {', '.join(missing_fields)}")

    dates = _daily_list(daily, "time")
    if not dates:
        return []
    timestamp = _date_to_timestamp(str(dates[0]))
    precipitation = _sum_numbers(_daily_list(daily, "precipitation_sum"))
    temp_max = _max_number(_daily_list(daily, "temperature_2m_max"))
    temp_min = _min_number(_daily_list(daily, "temperature_2m_min"))

    rows = [
        IndustryDataCreate(
            source_key=f"open_meteo:{location.key}:precip:{timestamp.date().isoformat()}",
            symbol=location.symbol,
            data_type="weather_precip_7d",
            value=precipitation,
            unit="mm",
            source=f"open_meteo:{location.key}",
            timestamp=timestamp,
        )
    ]
    if temp_max is not None:
        rows.append(
            IndustryDataCreate(
                source_key=f"open_meteo:{location.key}:tmax:{timestamp.date().isoformat()}",
                symbol=location.symbol,
                data_type="weather_temp_max_7d",
                value=temp_max,
                unit="C",
                source=f"open_meteo:{location.key}",
                timestamp=timestamp,
            )
        )
    if temp_min is not None:
        rows.append(
            IndustryDataCreate(
                source_key=f"open_meteo:{location.key}:tmin:{timestamp.date().isoformat()}",
                symbol=location.symbol,
                data_type="weather_temp_min_7d",
                value=temp_min,
                unit="C",
                source=f"open_meteo:{location.key}",
                timestamp=timestamp,
            )
        )
    return rows


def _date_to_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=CHINA_TZ)


def _daily_list(daily: dict[str, Any], field: str) -> list[Any]:
    values = daily[field]
    if not isinstance(values, list):
        raise RuntimeError(f"Open-Meteo daily field must be a list: {field}")
    return values


def _numbers(values: list[Any]) -> list[float]:
    numbers = []
    for value in values:
        if value is None:
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _sum_numbers(values: list[Any]) -> float:
    return round(sum(_numbers(values)), 4)


def _max_number(values: list[Any]) -> float | None:
    numbers = _numbers(values)
    return max(numbers) if numbers else None


def _min_number(values: list[Any]) -> float | None:
    numbers = _numbers(values)
    return min(numbers) if numbers else None
