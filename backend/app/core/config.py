from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"
    API_PREFIX: str = "/api"
    # Timestamps are stored in UTC; calendar days ("today", dose dates) are in this zone.
    APP_TIMEZONE: str = "Asia/Kolkata"

    # CORS — comma-separated allowed origins (frontend dev server)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    DATABASE_URL: str = "postgresql+psycopg://phia:phia@localhost:5432/phia"
    # Dev runner only (scripts/dev.py): folder of a portable Postgres install with
    # pgsql/bin and data/ inside. Empty = use Docker (or a Postgres already running).
    LOCAL_PG_HOME: str = ""

    # Vector store. CHROMA_MODE="embedded" (default, local dev) runs Chroma in-process
    # with persistence at CHROMA_PATH, so no separate server is needed. "http" talks to
    # a separate Chroma server at CHROMA_HOST:CHROMA_PORT; "cloud" talks to Chroma Cloud
    # via CHROMA_API_KEY/CHROMA_TENANT/CHROMA_DATABASE.
    CHROMA_MODE: str = "embedded"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    CHROMA_PATH: str = "chroma_data"
    # Chroma Cloud credentials (only used when CHROMA_MODE="cloud").
    CHROMA_API_KEY: str = ""
    CHROMA_TENANT: str = ""
    CHROMA_DATABASE: str = ""

    # Auth (dev default is >=32 bytes; override in any real deployment)
    SECRET_KEY: str = "dev-only-change-me-in-prod-0123456789abcdef"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # File uploads (lab reports)
    UPLOAD_DIR: str = "uploads"

    # Memory Agent retrieval (D2)
    MEMORY_TOPK: int = 5
    RECENT_WINDOW_DAYS: int = 180

    # Reasoning constants (OQ2/3/5)
    RESOLVE_AFTER_DAYS: int = 90
    CLUSTER_WINDOW_HOURS: int = 48
    MISSING_BP_DAYS: int = 60

    # LLM resilience: request timeout, and retries on the Groq fallback.
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_RETRIES: int = 2

    # ---- v2 LLM routing (memory.md D15): every call goes through app/core/llm.py ----
    # Primary: the LiteLLM proxy (OpenAI-compatible). Check names via GET {LLM_BASE_URL}/v1/models.
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    MODEL_FAST: str = "claude-haiku-5-5"  # small jobs: routing, parsing, extraction
    MODEL_SMART: str = "claude-sonnet-5-5"  # anything a person reads
    MODEL_VISION: str = "claude-sonnet-5-5"  # report photos and scans (Phase 4)
    # Which tier each task uses. Override with JSON in .env, e.g. LLM_TASK_TIERS='{"story":"fast"}'.
    LLM_TASK_TIERS: dict[str, str] = {
        "router": "fast",
        "intake": "fast",
        "report_extract": "fast",
        "report_summary": "smart",
        "observations": "smart",
        "drug_reference": "smart",
        "story": "smart",
        "assistant": "smart",
        "report_vision": "vision",
        "report_explainer": "smart",
        "report_questions": "smart",
        "brand_generic": "fast",
        "med_label": "smart",
        "med_ai_flag": "smart",
        "visit_structure": "smart",
    }
    # Fallback when the proxy fails or isn't configured: Groq. GROQ_API_KEY still works (v1 name).
    FALLBACK_BASE_URL: str = "https://api.groq.com/openai/v1"
    FALLBACK_API_KEY: str = Field(
        default="", validation_alias=AliasChoices("FALLBACK_API_KEY", "GROQ_API_KEY")
    )
    FALLBACK_MODEL: str = "openai/gpt-oss-120b"  # Groq retired llama-3.3-70b-versatile
    FALLBACK_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # report photos/scans
    # Fail over fast: short connect timeout, at most one retry on the proxy.
    LLM_CONNECT_TIMEOUT: float = 5.0
    LLM_PRIMARY_MAX_RETRIES: int = 1
    # Estimated USD per 1M tokens [input, output]; LiteLLM's own cost header wins when present.
    LLM_PRICES: dict[str, list[float]] = {
        "claude-sonnet-5-5": [2.0, 10.0],
        "claude-haiku-5-5": [0.10, 0.50],
        "openai/gpt-oss-120b": [0.0, 0.0],  # Groq free tier
    }
    # One JSON line per LLM call (task, model, tokens, cost; never prompt text). Empty = off.
    LLM_USAGE_LOG: str = "llm_usage.jsonl"
    # Speech-to-text for visit recaps (Phase 3), on the Groq key.
    STT_MODEL: str = "whisper-large-v3-turbo"
    # openFDA drug labels (Phase 5); optional, raises the rate limit.
    OPENFDA_API_KEY: str = ""
    # Level-3 "AI flag (unverified)" medication findings (Phase 5). Off = sourced-only.
    MED_AI_FLAGS_ENABLED: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
