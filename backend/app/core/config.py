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
    # Hand long closed-loop studies to an RQ worker instead of running them in the request.
    # Off by default: a single-machine offline deployment has no worker process, and a
    # study that is queued but never picked up is worse than one that simply blocks.
    background_optimization: bool = Field(
        default=False,
        description="启用后，闭环寻优交由 RQ Worker 执行；Redis 或 Worker 不可用时自动回退为同步执行。",
    )
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

    # Large-language-model provider. Empty/"none" keeps the system on its deterministic
    # path, which is the supported offline default: the venue may have no network.
    # Any OpenAI-compatible endpoint works — DeepSeek, Ollama, vLLM, Xinference, or a
    # self-hosted ChatGLM/LLaMA.
    llm_provider: str = Field(
        default="none",
        description='LLM 提供方标识；"none" 表示禁用，系统使用确定性规则解析。',
    )
    llm_base_url: str = Field(
        default="",
        description="OpenAI 兼容的 chat/completions 基址，例如 http://localhost:11434/v1。",
    )
    llm_model: str = Field(default="", description="模型名称，例如 deepseek-chat 或 qwen2.5:7b。")
    llm_api_key: str = Field(default="", description="API Key；本地 Ollama 等可留空。")
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
