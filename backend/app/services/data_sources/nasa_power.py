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


async def collect_nasa_power_weather_baselines(
    *,
    locations: tuple[WeatherLocation, ...] = DEFAULT_WEATHER_LOCATIONS,
    end: date | None = None,
    years: int = 5,
    window_days: int = 7,
    base_url: str = NASA_POWER_DAILY_API,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> list[IndustryDataCreate]:
    if years < 1:
        raise ValueError("NASA POWER baseline years must be at least 1")
    if window_days < 1:
        raise ValueError("NASA POWER baseline window days must be at least 1")

    target_end = end or (datetime.now(CHINA_TZ).date() - timedelta(days=1))
    windows = _historical_windows(target_end, years=years, window_days=window_days)
    if not windows:
        return []

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        rows: list[IndustryDataCreate] = []
        request_start = min(start for start, _ in windows)
        request_end = target_end
        for location in locations:
            response = await active_client.get(
                base_url,
                params={
                    "community": "AG",
                    "longitude": location.longitude,
                    "latitude": location.latitude,
                    "start": request_start.strftime("%Y%m%d"),
                    "end": request_end.strftime("%Y%m%d"),
                    "parameters": ",".join(POWER_DAILY_PARAMETERS),
                    "format": "JSON",
                    "time-standard": "UTC",
                },
            )
            response.raise_for_status()
            rows.extend(
                baseline_rows_from_power_payload(
                    location,
                    response.json(),
                    target_end=target_end,
                    windows=windows,
                    window_days=window_days,
                )
            )
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


def baseline_rows_from_power_payload(
    location: WeatherLocation,
    payload: dict[str, Any],
    *,
    target_end: date,
    windows: tuple[tuple[date, date], ...],
    window_days: int,
) -> list[IndustryDataCreate]:
    parameters = _parameter_payload(payload)
    missing = [field for field in POWER_DAILY_PARAMETERS if field not in parameters]
    if missing:
        raise RuntimeError(f"NASA POWER payload missing daily fields: {', '.join(missing)}")

    precipitation = _daily_mapping(parameters, "PRECTOTCORR")
    temp_max = _daily_mapping(parameters, "T2M_MAX")
    temp_min = _daily_mapping(parameters, "T2M_MIN")
    precip_windows: list[float] = []
    temp_windows: list[float] = []
    target_start = target_end - timedelta(days=window_days - 1)
    target_precip_values = _values_for_window(precipitation, target_start, target_end)
    target_temp_values = [
        *_values_for_window(temp_max, target_start, target_end),
        *_values_for_window(temp_min, target_start, target_end),
    ]
    target_precip = _sum_numbers(target_precip_values) if _numbers(target_precip_values) else None
    target_temp = _mean_number(target_temp_values)

    for start, end in windows:
        precip_values = _values_for_window(precipitation, start, end)
        temp_max_values = _values_for_window(temp_max, start, end)
        temp_min_values = _values_for_window(temp_min, start, end)
        if _numbers(precip_values):
            precip_windows.append(_sum_numbers(precip_values))
        temp_values = [*temp_max_values, *temp_min_values]
        temp_mean = _mean_number(temp_values)
        if temp_mean is not None:
            temp_windows.append(temp_mean)

    timestamp = datetime.combine(target_end, datetime.min.time()).replace(tzinfo=CHINA_TZ)
    year_range = f"{windows[0][0].year}-{windows[-1][1].year}"
    rows: list[IndustryDataCreate] = []
    if precip_windows:
        rows.append(
            IndustryDataCreate(
                source_key=(
                    f"nasa_power:{location.key}:baseline_precip:"
                    f"{year_range}:{target_end.strftime('%m%d')}:{window_days}d"
                ),
                symbol=location.symbol,
                data_type="weather_baseline_precip_7d",
                value=round(sum(precip_windows) / len(precip_windows), 4),
                unit="mm",
                source=f"nasa_power_baseline:{location.key}",
                timestamp=timestamp,
            )
        )
    if temp_windows:
        rows.append(
            IndustryDataCreate(
                source_key=(
                    f"nasa_power:{location.key}:baseline_temp_mean:"
                    f"{year_range}:{target_end.strftime('%m%d')}:{window_days}d"
                ),
                symbol=location.symbol,
                data_type="weather_baseline_temp_mean_7d",
                value=round(sum(temp_windows) / len(temp_windows), 4),
                unit="C",
                source=f"nasa_power_baseline:{location.key}",
                timestamp=timestamp,
            )
        )
    if target_precip is not None and precip_windows:
        rows.append(
            IndustryDataCreate(
                source_key=(
                    f"nasa_power:{location.key}:precip_pctile:"
                    f"{year_range}:{target_end.strftime('%m%d')}:{window_days}d"
                ),
                symbol=location.symbol,
                data_type="weather_precip_pctile_7d",
                value=_percentile_rank(target_precip, precip_windows),
                unit="pctile",
                source=f"nasa_power_baseline:{location.key}",
                timestamp=timestamp,
            )
        )
    if target_temp is not None and temp_windows:
        rows.append(
            IndustryDataCreate(
                source_key=(
                    f"nasa_power:{location.key}:temp_pctile:"
                    f"{year_range}:{target_end.strftime('%m%d')}:{window_days}d"
                ),
                symbol=location.symbol,
                data_type="weather_temp_pctile_7d",
                value=_percentile_rank(target_temp, temp_windows),
                unit="pctile",
                source=f"nasa_power_baseline:{location.key}",
                timestamp=timestamp,
            )
        )
    return rows


def _historical_windows(
    target_end: date,
    *,
    years: int,
    window_days: int,
) -> tuple[tuple[date, date], ...]:
    windows: list[tuple[date, date]] = []
    for year in range(target_end.year - years, target_end.year):
        window_end = _same_month_day(target_end, year)
        windows.append((window_end - timedelta(days=window_days - 1), window_end))
    return tuple(windows)


def _same_month_day(value: date, year: int) -> date:
    try:
        return value.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _values_for_window(values: dict[str, Any], start: date, end: date) -> list[Any]:
    items: list[Any] = []
    current = start
    while current <= end:
        items.append(values.get(current.strftime("%Y%m%d")))
        current += timedelta(days=1)
    return items


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


def _mean_number(values: Any) -> float | None:
    numbers = _numbers(values)
    return round(sum(numbers) / len(numbers), 4) if numbers else None


def _percentile_rank(value: float, sample: list[float]) -> float:
    if not sample:
        return 50.0
    less = sum(1 for item in sample if item < value)
    equal = sum(1 for item in sample if item == value)
    return round(((less + equal * 0.5) / len(sample)) * 100, 2)


def _max_number(values: Any) -> float | None:
    numbers = _numbers(values)
    return max(numbers) if numbers else None


def _min_number(values: Any) -> float | None:
    numbers = _numbers(values)
    return min(numbers) if numbers else None
