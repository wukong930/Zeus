from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.schemas.common import IndustryDataCreate, MarketDataCreate
from app.services.data_sources.akshare_futures import (
    collect_akshare_market_data,
    parse_akshare_symbols,
)
from app.services.data_sources.accuweather import collect_accuweather_current_conditions
from app.services.data_sources.eia import collect_eia_indicators
from app.services.data_sources.fred import collect_fred_indicators
from app.services.data_sources.nasa_power import collect_nasa_power_weather
from app.services.data_sources.noaa_cdo import collect_noaa_cdo_daily_summaries
from app.services.data_sources.open_meteo import collect_open_meteo_weather
from app.services.data_sources.rubber_spot import (
    collect_rubber_spot_indicators,
    parse_rubber_spot_symbols,
)
from app.services.data_sources.shipping_index import (
    collect_shipping_index_indicators,
    parse_shipping_index_symbols,
)
from app.services.data_sources.tushare_futures import (
    DEFAULT_TUSHARE_EXCHANGES,
    DEFAULT_TUSHARE_SYMBOLS,
    collect_tushare_market_data,
    parse_csv_tuple,
)
from app.services.etl.writers import append_industry_data, append_market_data

CATEGORY_BY_SYMBOL = {
    "RB": "ferrous",
    "HC": "ferrous",
    "I": "ferrous",
    "J": "ferrous",
    "JM": "ferrous",
    "RU": "rubber",
    "NR": "rubber",
    "BR": "rubber",
    "SC": "energy",
    "TA": "chemical",
    "MA": "chemical",
    "PP": "chemical",
    "CU": "metals",
    "AL": "metals",
    "ZN": "metals",
    "NI": "metals",
    "M": "agri",
    "Y": "agri",
    "P": "agri",
    "AU": "precious_metals",
    "AG": "precious_metals",
}


@dataclass(frozen=True)
class FreeDataIngestResult:
    market_rows: int = 0
    industry_rows: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    contexts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "degraded" if self.errors else "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "degraded": bool(self.errors),
            "market_rows": self.market_rows,
            "industry_rows": self.industry_rows,
            "source_counts": self.source_counts,
            "errors": self.errors,
            "contexts": len(self.contexts),
        }


async def run_free_data_ingest(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
) -> FreeDataIngestResult:
    current = settings or get_settings()
    market_payloads: list[MarketDataCreate] = []
    industry_payloads: list[IndustryDataCreate] = []
    source_counts: dict[str, int] = {}
    errors: list[dict[str, str]] = []

    if current.data_source_akshare_enabled:
        try:
            akshare_result = await collect_akshare_market_data(
                symbols=parse_akshare_symbols(current.data_source_akshare_symbols),
                limit=current.data_source_akshare_history_limit,
            )
            market_payloads.extend(akshare_result.rows)
            errors.extend(sanitize_source_errors(akshare_result.errors))
            source_counts["akshare"] = len(akshare_result.rows)
        except Exception as exc:
            errors.append({"source": "akshare", "error": safe_error_message(exc)})

    if current.data_source_open_meteo_enabled:
        try:
            weather_rows = await collect_open_meteo_weather(base_url=current.open_meteo_base_url)
            industry_payloads.extend(weather_rows)
            source_counts["open_meteo"] = len(weather_rows)
        except Exception as exc:
            errors.append({"source": "open_meteo", "error": safe_error_message(exc)})

    if current.data_source_nasa_power_enabled:
        try:
            nasa_rows = await collect_nasa_power_weather(base_url=current.nasa_power_base_url)
            industry_payloads.extend(nasa_rows)
            source_counts["nasa_power"] = len(nasa_rows)
        except Exception as exc:
            errors.append({"source": "nasa_power", "error": safe_error_message(exc)})

    if current.data_source_accuweather_enabled:
        if current.accuweather_api_key:
            try:
                accuweather_rows = await collect_accuweather_current_conditions(
                    api_key=current.accuweather_api_key,
                    base_url=current.accuweather_base_url,
                    max_locations=current.accuweather_max_locations_per_run,
                )
                industry_payloads.extend(accuweather_rows)
                source_counts["accuweather"] = len(accuweather_rows)
            except Exception as exc:
                errors.append({"source": "accuweather", "error": safe_error_message(exc, current.accuweather_api_key)})
        else:
            source_counts["accuweather"] = 0
            errors.append({"source": "accuweather", "error": "enabled source missing ACCUWEATHER_API_KEY"})

    if current.data_source_noaa_cdo_enabled:
        if current.noaa_cdo_api_key:
            try:
                noaa_rows = await collect_noaa_cdo_daily_summaries(
                    api_key=current.noaa_cdo_api_key,
                    base_url=current.noaa_cdo_base_url,
                    max_locations=current.noaa_cdo_max_locations_per_run,
                    station_radius_degrees=current.noaa_cdo_station_radius_degrees,
                    max_station_candidates=current.noaa_cdo_max_station_candidates,
                )
                industry_payloads.extend(noaa_rows)
                source_counts["noaa_cdo"] = len(noaa_rows)
            except Exception as exc:
                errors.append({"source": "noaa_cdo", "error": safe_error_message(exc, current.noaa_cdo_api_key)})
        else:
            source_counts["noaa_cdo"] = 0
            errors.append({"source": "noaa_cdo", "error": "enabled source missing NOAA_CDO_API_KEY"})

    if current.data_source_fred_enabled:
        if current.fred_api_key:
            try:
                fred_rows = await collect_fred_indicators(
                    api_key=current.fred_api_key,
                    base_url=current.fred_base_url,
                )
                industry_payloads.extend(fred_rows)
                source_counts["fred"] = len(fred_rows)
            except Exception as exc:
                errors.append({"source": "fred", "error": safe_error_message(exc, current.fred_api_key)})
        else:
            source_counts["fred"] = 0
            errors.append({"source": "fred", "error": "enabled source missing FRED_API_KEY"})

    if current.data_source_eia_enabled:
        if current.eia_api_key:
            try:
                eia_rows = await collect_eia_indicators(
                    api_key=current.eia_api_key,
                    base_url=current.eia_base_url,
                )
                industry_payloads.extend(eia_rows)
                source_counts["eia"] = len(eia_rows)
            except Exception as exc:
                errors.append({"source": "eia", "error": safe_error_message(exc, current.eia_api_key)})
        else:
            source_counts["eia"] = 0
            errors.append({"source": "eia", "error": "enabled source missing EIA_API_KEY"})

    if current.data_source_tushare_enabled:
        if current.tushare_token:
            try:
                tushare_result = await collect_tushare_market_data(
                    token=current.tushare_token,
                    base_url=current.tushare_base_url,
                    exchanges=parse_csv_tuple(
                        current.data_source_tushare_exchanges,
                        DEFAULT_TUSHARE_EXCHANGES,
                    ),
                    symbols=parse_csv_tuple(
                        current.data_source_tushare_symbols,
                        DEFAULT_TUSHARE_SYMBOLS,
                    ),
                )
                market_payloads.extend(tushare_result.rows)
                errors.extend(sanitize_source_errors(tushare_result.errors, current.tushare_token))
                source_counts["tushare"] = len(tushare_result.rows)
            except Exception as exc:
                errors.append({"source": "tushare", "error": safe_error_message(exc, current.tushare_token)})
        else:
            source_counts["tushare"] = 0
            errors.append({"source": "tushare", "error": "enabled source missing TUSHARE_TOKEN"})

    if current.data_source_rubber_spot_enabled:
        try:
            rubber_spot_result = await collect_rubber_spot_indicators(
                symbols=parse_rubber_spot_symbols(current.data_source_rubber_spot_symbols),
                history_days=current.data_source_rubber_spot_history_days,
            )
            industry_payloads.extend(rubber_spot_result.rows)
            errors.extend(sanitize_source_errors(rubber_spot_result.errors))
            source_counts["rubber_spot"] = len(rubber_spot_result.rows)
        except Exception as exc:
            errors.append({"source": "rubber_spot", "error": safe_error_message(exc)})

    if current.data_source_shipping_index_enabled:
        if current.shipping_index_url:
            try:
                shipping_index_rows = await collect_shipping_index_indicators(
                    url=current.shipping_index_url,
                    symbols=parse_shipping_index_symbols(current.shipping_index_symbols),
                    timeout=current.shipping_index_timeout_seconds,
                )
                industry_payloads.extend(shipping_index_rows)
                source_counts["shipping_index"] = len(shipping_index_rows)
            except Exception as exc:
                errors.append({"source": "shipping_index", "error": safe_error_message(exc)})
        else:
            source_counts["shipping_index"] = 0
            errors.append({"source": "shipping_index", "error": "enabled source missing SHIPPING_INDEX_URL"})

    if market_payloads:
        await append_market_data(session, market_payloads)
    if industry_payloads:
        await append_industry_data(session, industry_payloads)

    return FreeDataIngestResult(
        market_rows=len(market_payloads),
        industry_rows=len(industry_payloads),
        source_counts=source_counts,
        errors=errors,
        contexts=market_context_payloads(market_payloads),
    )


def market_context_payloads(rows: list[MarketDataCreate], *, per_symbol_limit: int = 80) -> list[dict[str, Any]]:
    rows_by_symbol: dict[str, list[MarketDataCreate]] = defaultdict(list)
    for row in rows:
        rows_by_symbol[row.symbol].append(row)

    contexts = []
    for symbol, symbol_rows in rows_by_symbol.items():
        ordered = sorted(symbol_rows, key=lambda item: item.timestamp)[-per_symbol_limit:]
        latest = ordered[-1]
        contexts.append(
            {
                "symbol1": symbol,
                "category": CATEGORY_BY_SYMBOL.get(symbol, "unknown"),
                "timestamp": latest.timestamp.isoformat(),
                "regime": "free_data_ingest",
                "market_data": [
                    {
                        "timestamp": row.timestamp.isoformat(),
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                        "open_interest": row.open_interest,
                    }
                    for row in ordered
                ],
                "source": "free_data_ingest",
            }
        )
    return contexts


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_source_errors(
    errors: list[dict[str, str]],
    *secrets: str | None,
) -> list[dict[str, str]]:
    return [
        {
            **error,
            "error": safe_error_message(error.get("error", ""), *secrets),
        }
        for error in errors
    ]


def safe_error_message(error: object, *secrets: str | None) -> str:
    message = str(error)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"([?&](?:api_key|token)=)[^&\s']+", r"\1[redacted]", message)
    return message
