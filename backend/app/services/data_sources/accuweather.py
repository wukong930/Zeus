from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.schemas.common import IndustryDataCreate
from app.services.data_sources.open_meteo import DEFAULT_WEATHER_LOCATIONS, WeatherLocation

ACCUWEATHER_BASE_URL = "https://dataservice.accuweather.com"


async def collect_accuweather_current_conditions(
    *,
    api_key: str,
    locations: tuple[WeatherLocation, ...] = DEFAULT_WEATHER_LOCATIONS,
    base_url: str = ACCUWEATHER_BASE_URL,
    max_locations: int | None = None,
    timeout: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    if not api_key.strip():
        raise ValueError("AccuWeather API key is required")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept-Encoding": "gzip,deflate",
        }
        scoped_locations = locations[:max_locations] if max_locations is not None else locations
        for location in scoped_locations:
            location_key = await _location_key_for_coordinates(
                active_client,
                base_url=base_url,
                headers=headers,
                location=location,
            )
            response = await active_client.get(
                f"{base_url.rstrip('/')}/currentconditions/v1/{location_key}",
                params={"details": "true"},
                headers=headers,
            )
            response.raise_for_status()
            rows.extend(rows_from_current_conditions_payload(location, response.json()))
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


def rows_from_current_conditions_payload(
    location: WeatherLocation,
    payload: Any,
) -> list[IndustryDataCreate]:
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("AccuWeather current conditions payload must be a non-empty list")
    item = payload[0]
    if not isinstance(item, dict):
        raise RuntimeError("AccuWeather current conditions item must be an object")

    observed_at = _observation_time(item)
    rows: list[IndustryDataCreate] = []
    temperature = _metric_value(item.get("Temperature"))
    precip_1h = _metric_value(item.get("Precip1hr"))
    humidity = _float_value(item.get("RelativeHumidity"))
    wind_speed = _metric_value(_nested(item, "Wind", "Speed"))

    if temperature is not None:
        rows.append(
            _row(
                location,
                data_type="weather_temp_current_c",
                value=temperature,
                unit="C",
                timestamp=observed_at,
                suffix="temp",
            )
        )
    if precip_1h is not None:
        rows.append(
            _row(
                location,
                data_type="weather_precip_1h",
                value=precip_1h,
                unit="mm",
                timestamp=observed_at,
                suffix="precip1h",
            )
        )
    if humidity is not None:
        rows.append(
            _row(
                location,
                data_type="weather_humidity_pct",
                value=humidity,
                unit="pct",
                timestamp=observed_at,
                suffix="humidity",
            )
        )
    if wind_speed is not None:
        rows.append(
            _row(
                location,
                data_type="weather_wind_kph",
                value=wind_speed,
                unit="km/h",
                timestamp=observed_at,
                suffix="wind",
            )
        )
    return rows


async def _location_key_for_coordinates(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    location: WeatherLocation,
) -> str:
    response = await client.get(
        f"{base_url.rstrip('/')}/locations/v1/cities/geoposition/search",
        params={"q": f"{location.latitude},{location.longitude}", "topLevel": "true"},
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("Key"):
        raise RuntimeError("AccuWeather location lookup payload missing Key")
    return str(payload["Key"])


def _row(
    location: WeatherLocation,
    *,
    data_type: str,
    value: float,
    unit: str,
    timestamp: datetime,
    suffix: str,
) -> IndustryDataCreate:
    return IndustryDataCreate(
        source_key=f"accuweather:{location.key}:{suffix}:{timestamp.date().isoformat()}",
        symbol=location.symbol,
        data_type=data_type,
        value=round(value, 4),
        unit=unit,
        source=f"accuweather:{location.key}",
        timestamp=timestamp,
    )


def _observation_time(item: dict[str, Any]) -> datetime:
    value = item.get("LocalObservationDateTime")
    if not isinstance(value, str) or not value:
        raise RuntimeError("AccuWeather payload missing LocalObservationDateTime")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _metric_value(value: Any) -> float | None:
    metric = _nested(value, "Metric")
    if not isinstance(metric, dict):
        return None
    return _float_value(metric.get("Value"))


def _nested(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
