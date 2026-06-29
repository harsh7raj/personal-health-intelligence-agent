from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+psycopg://phia:phia@localhost:5432/phia"

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
