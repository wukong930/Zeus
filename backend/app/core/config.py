from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Zeus API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "info"

    database_url: str = Field(
        default="postgresql+asyncpg://zeus:zeus@localhost:55432/zeus",
        description="Async SQLAlchemy database URL.",
    )
    database_pool_size: int = 10
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    llm_model: str | None = None
    llm_timeout_seconds: float = 120.0
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    data_source_akshare_enabled: bool = False
    data_source_akshare_symbols: str = (
        "RB0,HC0,I0,J0,JM0,RU0,NR0,BR0,SC0,TA0,MA0,PP0,CU0,AL0,ZN0,NI0,M0,Y0,P0,AU0,AG0"
    )
    data_source_akshare_history_limit: int = 80
    data_source_gdelt_enabled: bool = False
    data_source_gdelt_query: str = "commodities futures OR supply chain OR inventory"
    data_source_open_meteo_enabled: bool = False
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    data_source_nasa_power_enabled: bool = False
    nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    data_source_nasa_power_baseline_enabled: bool = False
    nasa_power_baseline_years: int = Field(default=5, ge=1, le=30)
    nasa_power_baseline_window_days: int = Field(default=7, ge=1, le=45)
    data_source_noaa_cdo_enabled: bool = False
    noaa_cdo_api_key: str | None = None
    noaa_cdo_base_url: str = "https://www.ncei.noaa.gov/cdo-web/api/v2"
    noaa_cdo_max_locations_per_run: int = Field(default=3, ge=1, le=20)
    noaa_cdo_station_radius_degrees: float = Field(default=1.5, ge=0.1, le=10.0)
    noaa_cdo_max_station_candidates: int = Field(default=5, ge=1, le=50)
    data_source_accuweather_enabled: bool = False
    accuweather_api_key: str | None = None
    accuweather_base_url: str = "https://dataservice.accuweather.com"
    accuweather_max_locations_per_run: int = Field(default=4, ge=1, le=20)
    data_source_fred_enabled: bool = False
    fred_api_key: str | None = None
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    data_source_eia_enabled: bool = False
    eia_api_key: str | None = None
    eia_base_url: str = "https://api.eia.gov"
    data_source_tushare_enabled: bool = False
    tushare_token: str | None = None
    tushare_base_url: str = "http://api.tushare.pro"
    data_source_tushare_exchanges: str = "SHFE,DCE,CZCE,INE"
    data_source_tushare_symbols: str = (
        "RB,HC,I,J,JM,RU,NR,BR,SC,TA,MA,PP,CU,AL,ZN,NI,M,Y,P,AU,AG"
    )
    data_source_rubber_spot_enabled: bool = False
    data_source_rubber_spot_symbols: str = "RU,NR,BR"
    data_source_rubber_spot_history_days: int = Field(default=7, ge=1, le=30)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        enable_decoding=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
