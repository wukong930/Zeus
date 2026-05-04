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
