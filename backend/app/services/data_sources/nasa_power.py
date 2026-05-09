from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas.common import IndustryDataCreate
from app.services.data_sources.open_meteo import DEFAULT_WEATHER_LOCATIONS, WeatherLocation

NASA_POWER_DAILY_API = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_DAILY_PARAMETERS = ("PRECTOTCORR", "T2M_MAX", "T2M_MIN")
CHINA_TZ = ZoneInfo("Asia/Shanghai")


async def collect_nasa_power_weather(
    *,
    locations: tuple[WeatherLocation, ...] = DEFAULT_WEATHER_LOCATIONS,
    start: date | None = None,
    end: date | None = None,
    base_url: str = NASA_POWER_DAILY_API,
    timeout: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    end_date = end or (datetime.now(CHINA_TZ).date() - timedelta(days=1))
    start_date = start or (end_date - timedelta(days=6))
    if start_date > end_date:
        raise ValueError("NASA POWER start date must be before or equal to end date")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        for location in locations:
            response = await active_client.get(
                base_url,
                params={
                    "community": "AG",
                    "longitude": location.longitude,
                    "latitude": location.latitude,
                    "start": start_date.strftime("%Y%m%d"),
                    "end": end_date.strftime("%Y%m%d"),
                    "parameters": ",".join(POWER_DAILY_PARAMETERS),
                    "format": "JSON",
                    "time-standard": "UTC",
                },
            )
            response.raise_for_status()
            rows.extend(rows_from_power_payload(location, response.json()))
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


def rows_from_power_payload(
    location: WeatherLocation,
    payload: dict[str, Any],
) -> list[IndustryDataCreate]:
    parameters = _parameter_payload(payload)
    missing = [field for field in POWER_DAILY_PARAMETERS if field not in parameters]
    if missing:
        raise RuntimeError(f"NASA POWER payload missing daily fields: {', '.join(missing)}")

    precipitation = _daily_mapping(parameters, "PRECTOTCORR")
    temp_max = _daily_mapping(parameters, "T2M_MAX")
    temp_min = _daily_mapping(parameters, "T2M_MIN")
    dates = sorted({*precipitation.keys(), *temp_max.keys(), *temp_min.keys()})
    if not dates:
        return []

    timestamp = _power_date_to_timestamp(dates[-1])
    window = f"{dates[0]}-{dates[-1]}"
    precip_value = _sum_numbers(precipitation.values())
    max_value = _max_number(temp_max.values())
    min_value = _min_number(temp_min.values())

    rows = [
        IndustryDataCreate(
            source_key=f"nasa_power:{location.key}:precip:{window}",
            symbol=location.symbol,
            data_type="weather_precip_7d",
            value=precip_value,
            unit="mm",
            source=f"nasa_power:{location.key}",
            timestamp=timestamp,
        )
    ]
    if max_value is not None:
        rows.append(
            IndustryDataCreate(
                source_key=f"nasa_power:{location.key}:tmax:{window}",
                symbol=location.symbol,
                data_type="weather_temp_max_7d",
                value=max_value,
                unit="C",
                source=f"nasa_power:{location.key}",
                timestamp=timestamp,
            )
        )
    if min_value is not None:
        rows.append(
            IndustryDataCreate(
                source_key=f"nasa_power:{location.key}:tmin:{window}",
                symbol=location.symbol,
                data_type="weather_temp_min_7d",
                value=min_value,
                unit="C",
                source=f"nasa_power:{location.key}",
                timestamp=timestamp,
            )
        )
    return rows


def _parameter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("NASA POWER payload missing properties")
    parameters = properties.get("parameter")
    if not isinstance(parameters, dict):
        raise RuntimeError("NASA POWER payload missing properties.parameter")
    return parameters


def _daily_mapping(parameters: dict[str, Any], field: str) -> dict[str, Any]:
    values = parameters[field]
    if not isinstance(values, dict):
        raise RuntimeError(f"NASA POWER daily field must be an object: {field}")
    return values


def _power_date_to_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=CHINA_TZ)


def _numbers(values: Any) -> list[float]:
    numbers: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number <= -998:
            continue
        numbers.append(number)
    return numbers


def _sum_numbers(values: Any) -> float:
    return round(sum(_numbers(values)), 4)


def _max_number(values: Any) -> float | None:
    numbers = _numbers(values)
    return max(numbers) if numbers else None


def _min_number(values: Any) -> float | None:
    numbers = _numbers(values)
    return min(numbers) if numbers else None
