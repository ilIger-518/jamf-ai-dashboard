"""Application settings loaded from environment variables via pydantic-settings."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://jamfdash:changeme@localhost:5432/jamfdash"

    # ── Redis ───────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Security ────────────────────────────────────────────────
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Fernet key for encrypting Jamf credentials at rest
    fernet_key: str = ""

    # ── ChromaDB ────────────────────────────────────────────────
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # ── Ollama / LLM ────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    embedding_model_name: str = "nomic-embed-text"
    llm_temperature: float = 0.2
    llm_context_window: int = 4096
    llm_timeout_seconds: int = 180

    # ── Sync ────────────────────────────────────────────────────
    sync_interval_minutes: int = 15

    # ── CORS ────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_origin_regex: str | None = r"^https?://([a-zA-Z0-9.-]+)(:\\d+)?$"

    # ── Cookie ──────────────────────────────────────────────────
    cookie_secure: bool = False  # set True in production (requires HTTPS)

    # ── Logging ─────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.secret_key != "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
