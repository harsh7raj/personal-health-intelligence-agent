from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"
    API_PREFIX: str = "/api"

    # CORS — comma-separated allowed origins (frontend dev server)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    DATABASE_URL: str = "postgresql+psycopg://phia:phia@localhost:5432/phia"

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

    # Auth (dev default is >=32 bytes; override in any real deployment)
    SECRET_KEY: str = "dev-only-change-me-in-prod-0123456789abcdef"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # File uploads (lab reports)
    UPLOAD_DIR: str = "uploads"

    # LLM — Intake parsing via Groq (OpenAI-compatible API). See memory.md D7.
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    INTAKE_MODEL: str = "llama-3.3-70b-versatile"

    # Memory Agent retrieval (D2)
    MEMORY_TOPK: int = 5
    RECENT_WINDOW_DAYS: int = 180

    # Reasoning + Response LLM (Groq, D8)
    REASONING_MODEL: str = "llama-3.3-70b-versatile"
    RESPONSE_MODEL: str = "llama-3.3-70b-versatile"

    # Reasoning constants (OQ2/3/5)
    RESOLVE_AFTER_DAYS: int = 90
    CLUSTER_WINDOW_HOURS: int = 48
    MISSING_BP_DAYS: int = 60

    # LLM resilience (Phase 8)
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_RETRIES: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
