from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from app.schemas.common import IndustryDataCreate
from app.services.data_sources.open_meteo import CHINA_TZ, DEFAULT_WEATHER_LOCATIONS, WeatherLocation

NOAA_CDO_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"
NOAA_DAILY_DATASET = "GHCND"
NOAA_DAILY_DATATYPES = ("PRCP", "TMAX", "TMIN")


@dataclass(frozen=True)
class NoaaStationCandidate:
    id: str
    name: str
    latitude: float
    longitude: float
    datacoverage: float | None
    distance_km: float


async def collect_noaa_cdo_daily_summaries(
    *,
    api_key: str,
    locations: tuple[WeatherLocation, ...] = DEFAULT_WEATHER_LOCATIONS,
    end: date | None = None,
    days: int = 7,
    base_url: str = NOAA_CDO_BASE_URL,
    max_locations: int = 3,
    station_radius_degrees: float = 1.5,
    max_station_candidates: int = 5,
    timeout: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    if not api_key.strip():
        raise ValueError("NOAA CDO API key is required")
    if days < 1:
        raise ValueError("NOAA CDO days must be at least 1")

    target_end = end or date.today()
    target_start = target_end - timedelta(days=days - 1)
    headers = {"token": api_key}
    scoped_locations = locations[:max_locations]

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        for location in scoped_locations:
            stations = await stations_for_location(
                active_client,
                base_url=base_url,
                headers=headers,
                location=location,
                start=target_start,
                end=target_end,
                radius_degrees=station_radius_degrees,
                max_candidates=max_station_candidates,
            )
            rows.extend(
                await _best_rows_for_location(
                    active_client,
                    base_url=base_url,
                    headers=headers,
                    location=location,
                    stations=stations,
                    start=target_start,
                    end=target_end,
                )
            )
        return rows
    finally:
        if owns_client:
            await active_client.aclose()


async def station_for_location(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    location: WeatherLocation,
    radius_degrees: float = 1.5,
    max_candidates: int = 5,
) -> NoaaStationCandidate | None:
    stations = await stations_for_location(
        client,
        base_url=base_url,
        headers=headers,
        location=location,
        radius_degrees=radius_degrees,
        max_candidates=max_candidates,
    )
    return stations[0] if stations else None


async def stations_for_location(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    location: WeatherLocation,
    start: date | None = None,
    end: date | None = None,
    radius_degrees: float = 1.5,
    max_candidates: int = 5,
) -> list[NoaaStationCandidate]:
    lat_min = max(location.latitude - radius_degrees, -90.0)
    lat_max = min(location.latitude + radius_degrees, 90.0)
    lon_min = max(location.longitude - radius_degrees, -180.0)
    lon_max = min(location.longitude + radius_degrees, 180.0)
    params = {
        "datasetid": NOAA_DAILY_DATASET,
        "extent": f"{lat_min:.4f},{lon_min:.4f},{lat_max:.4f},{lon_max:.4f}",
        "limit": max_candidates,
        "sortfield": "datacoverage",
        "sortorder": "desc",
    }
    if start is not None and end is not None:
        params["startdate"] = start.isoformat()
        params["enddate"] = end.isoformat()
    response = await client.get(
        f"{base_url.rstrip('/')}/stations",
        params=params,
        headers=headers,
    )
    response.raise_for_status()
    results = _results_list(response.json(), "NOAA CDO station")
    candidates = [
        _station_candidate(location, item)
        for item in results
        if isinstance(item, dict) and item.get("id")
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return sorted(candidates, key=lambda item: (-(item.datacoverage or 0), item.distance_km))


async def _best_rows_for_location(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    location: WeatherLocation,
    stations: list[NoaaStationCandidate],
    start: date,
    end: date,
) -> list[IndustryDataCreate]:
    best_rows: list[IndustryDataCreate] = []
    best_coverage = 0
    for station in stations:
        payload = await _daily_data_for_station(
            client,
            base_url=base_url,
            headers=headers,
            station=station,
            start=start,
            end=end,
        )
        candidate_rows = rows_from_cdo_daily_payload(location, station, payload)
        candidate_coverage = len({row.data_type for row in candidate_rows})
        if candidate_coverage > best_coverage:
            best_rows = candidate_rows
            best_coverage = candidate_coverage
        if candidate_coverage == len(NOAA_DAILY_DATATYPES):
            return candidate_rows
    return best_rows


def rows_from_cdo_daily_payload(
    location: WeatherLocation,
    station: NoaaStationCandidate,
    payload: Any,
) -> list[IndustryDataCreate]:
    results = _results_list(payload, "NOAA CDO daily")
    grouped: dict[str, list[tuple[datetime, float]]] = {data_type: [] for data_type in NOAA_DAILY_DATATYPES}
    for item in results:
        if not isinstance(item, dict):
            continue
        data_type = item.get("datatype")
        if data_type not in grouped:
            continue
        timestamp = _parse_noaa_datetime(item.get("date"))
        value = _float_value(item.get("value"))
        if timestamp is not None and value is not None:
            grouped[data_type].append((timestamp, value))

    rows: list[IndustryDataCreate] = []
    precip = [value for _, value in grouped["PRCP"]]
    if precip:
        rows.append(
            _row(
                location,
                station=station,
                data_type="weather_precip_7d",
                value=sum(precip),
                unit="mm",
                timestamp=_latest_timestamp(grouped["PRCP"]),
                suffix="precip",
            )
        )

    tmax = [value for _, value in grouped["TMAX"]]
    if tmax:
        rows.append(
            _row(
                location,
                station=station,
                data_type="weather_temp_max_7d",
                value=max(tmax),
                unit="C",
                timestamp=_latest_timestamp(grouped["TMAX"]),
                suffix="tmax",
            )
        )

    tmin = [value for _, value in grouped["TMIN"]]
    if tmin:
        rows.append(
            _row(
                location,
                station=station,
                data_type="weather_temp_min_7d",
                value=min(tmin),
                unit="C",
                timestamp=_latest_timestamp(grouped["TMIN"]),
                suffix="tmin",
            )
        )
    return rows


async def _daily_data_for_station(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    station: NoaaStationCandidate,
    start: date,
    end: date,
) -> Any:
    response = await client.get(
        f"{base_url.rstrip('/')}/data",
        params={
            "datasetid": NOAA_DAILY_DATASET,
            "stationid": station.id,
            "startdate": start.isoformat(),
            "enddate": end.isoformat(),
            "datatypeid": ",".join(NOAA_DAILY_DATATYPES),
            "units": "metric",
            "limit": 1000,
            "includemetadata": "false",
        },
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


def _row(
    location: WeatherLocation,
    *,
    station: NoaaStationCandidate,
    data_type: str,
    value: float,
    unit: str,
    timestamp: datetime,
    suffix: str,
) -> IndustryDataCreate:
    station_key = station.id.replace(":", "-")
    return IndustryDataCreate(
        source_key=f"noaa_cdo:{location.key}:{station_key}:{suffix}:{timestamp.date().isoformat()}",
        symbol=location.symbol,
        data_type=data_type,
        value=round(value, 4),
        unit=unit,
        source=f"noaa_cdo:{location.key}",
        timestamp=timestamp,
    )


def _station_candidate(location: WeatherLocation, item: dict[str, Any]) -> NoaaStationCandidate | None:
    latitude = _float_value(item.get("latitude"))
    longitude = _float_value(item.get("longitude"))
    if latitude is None or longitude is None:
        return None
    return NoaaStationCandidate(
        id=str(item["id"]),
        name=str(item.get("name") or item["id"]),
        latitude=latitude,
        longitude=longitude,
        datacoverage=_float_value(item.get("datacoverage")),
        distance_km=_haversine_km(location.latitude, location.longitude, latitude, longitude),
    )


def _results_list(payload: Any, label: str) -> list[Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} payload must be an object")
    results = payload.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise RuntimeError(f"{label} payload results must be a list")
    return results


def _latest_timestamp(values: list[tuple[datetime, float]]) -> datetime:
    return max(timestamp for timestamp, _ in values)


def _parse_noaa_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(CHINA_TZ)
    except ValueError:
        return None


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(radius_km * 2 * asin(sqrt(a)), 3)
