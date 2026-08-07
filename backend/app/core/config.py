from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded only from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INDUSOPT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "IndusOpt API"
    app_version: str = "0.4.0"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+asyncpg://indusopt:indusopt@localhost:5432/indusopt",
        description="SQLAlchemy asynchronous database URL.",
    )
    redis_url: str = "redis://localhost:6379/0"
    artifact_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "data",
        description="Root directory for local simulation and model artifacts.",
    )
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
