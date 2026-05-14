from importlib.util import find_spec

from app.core.config import Settings, get_settings
from app.services.data_sources.types import DataSourceStatus


def data_source_statuses(settings: Settings | None = None) -> list[DataSourceStatus]:
    current = settings or get_settings()
    akshare_available = find_spec("akshare") is not None

    return [
        DataSourceStatus(
            id="akshare",
            name="AKShare futures",
            category="market_data",
            enabled=current.data_source_akshare_enabled,
            configured=current.data_source_akshare_enabled and akshare_available,
            requires_key=False,
            free_tier="free_no_key",
            status=_status(current.data_source_akshare_enabled, akshare_available),
            note=(
                "Chinese futures OHLCV, main contracts, warehouse receipts and rankings."
                if akshare_available
                else "Install the backend data dependency to enable AKShare."
            ),
        ),
        DataSourceStatus(
            id="gdelt",
            name="GDELT DOC 2.0",
            category="news_events",
            enabled=current.data_source_gdelt_enabled,
            configured=current.data_source_gdelt_enabled,
            requires_key=False,
            free_tier="free_no_key",
            status="ready" if current.data_source_gdelt_enabled else "disabled",
            note="Global news article search for commodity and supply-chain shocks.",
        ),
        DataSourceStatus(
            id="open_meteo",
            name="Open-Meteo",
            category="industry_data",
            enabled=current.data_source_open_meteo_enabled,
            configured=current.data_source_open_meteo_enabled,
            requires_key=False,
            free_tier="free_no_key",
            status="ready" if current.data_source_open_meteo_enabled else "disabled",
            note="Weather forecast and historical weather for origin-market shock detection.",
        ),
        DataSourceStatus(
            id="nasa_power",
            name="NASA POWER",
            category="industry_data",
            enabled=current.data_source_nasa_power_enabled,
            configured=current.data_source_nasa_power_enabled,
            requires_key=False,
            free_tier="free_no_key",
            status="ready" if current.data_source_nasa_power_enabled else "disabled",
            note="Daily agro-meteorological precipitation and temperature for regional baselines.",
        ),
        DataSourceStatus(
            id="nasa_power_baseline",
            name="NASA POWER seasonal baseline",
            category="industry_data",
            enabled=current.data_source_nasa_power_baseline_enabled,
            configured=current.data_source_nasa_power_baseline_enabled,
            requires_key=False,
            free_tier="free_no_key",
            status="ready" if current.data_source_nasa_power_baseline_enabled else "disabled",
            note="Same-calendar historical weather windows for precipitation and temperature anomalies.",
        ),
        DataSourceStatus(
            id="noaa_cdo",
            name="NOAA Climate Data Online",
            category="industry_data",
            enabled=current.data_source_noaa_cdo_enabled,
            configured=current.data_source_noaa_cdo_enabled and bool(_clean(current.noaa_cdo_api_key)),
            requires_key=True,
            free_tier="free_registration",
            status=_keyed_status(current.data_source_noaa_cdo_enabled, current.noaa_cdo_api_key),
            note="Official station-based historical climate data. Free token required.",
        ),
        DataSourceStatus(
            id="accuweather",
            name="AccuWeather Current Conditions",
            category="industry_data",
            enabled=current.data_source_accuweather_enabled,
            configured=current.data_source_accuweather_enabled and bool(_clean(current.accuweather_api_key)),
            requires_key=True,
            free_tier="free_registration_limited",
            status=_keyed_status(current.data_source_accuweather_enabled, current.accuweather_api_key),
            note="Coordinate-based current conditions for near-term regional weather overlays.",
        ),
        DataSourceStatus(
            id="fred",
            name="FRED",
            category="macro_data",
            enabled=current.data_source_fred_enabled,
            configured=current.data_source_fred_enabled and bool(_clean(current.fred_api_key)),
            requires_key=True,
            free_tier="free_registration",
            status=_keyed_status(current.data_source_fred_enabled, current.fred_api_key),
            note="Rates, dollar index and commodity reference series. Free key required.",
        ),
        DataSourceStatus(
            id="eia",
            name="EIA Open Data",
            category="energy_fundamentals",
            enabled=current.data_source_eia_enabled,
            configured=current.data_source_eia_enabled and bool(_clean(current.eia_api_key)),
            requires_key=True,
            free_tier="free_registration",
            status=_keyed_status(current.data_source_eia_enabled, current.eia_api_key),
            note="U.S. petroleum and natural gas fundamentals. Free key required.",
        ),
        DataSourceStatus(
            id="tushare",
            name="Tushare Pro",
            category="market_data",
            enabled=current.data_source_tushare_enabled,
            configured=current.data_source_tushare_enabled and bool(_clean(current.tushare_token)),
            requires_key=True,
            free_tier="free_registration_with_points",
            status=_keyed_status(current.data_source_tushare_enabled, current.tushare_token),
            note="Chinese futures backup feed. Token and sufficient points are required.",
        ),
        DataSourceStatus(
            id="rubber_spot",
            name="AKShare 100ppi rubber spot/basis",
            category="industry_data",
            enabled=current.data_source_rubber_spot_enabled,
            configured=current.data_source_rubber_spot_enabled and akshare_available,
            requires_key=False,
            free_tier="free_no_key",
            status=_status(current.data_source_rubber_spot_enabled, akshare_available),
            note="Natural-rubber spot price and basis for RU/NR/BR. No key required; availability depends on AKShare and 100ppi.",
        ),
    ]


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _status(enabled: bool, dependency_available: bool) -> str:
    if not enabled:
        return "disabled"
    return "ready" if dependency_available else "missing_dependency"


def _keyed_status(enabled: bool, key: str | None) -> str:
    if not enabled:
        return "disabled"
    return "ready" if _clean(key) else "missing_key"
