from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    user: str
    password: str
    host: str
    port: int
    dbname: str
    DATABASE_SSL: str = "require"
    JWT_SECRET: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSIONS: Literal[768] = 768
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "google/gemma-4-31b-it:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_TIMEOUT_SECONDS: float = 90
    # A range scan runs in the background, so it can outlast the browser's
    # request budget. Give slow models room instead of abandoning the chapter.
    STORY_BIBLE_TIMEOUT_SECONDS: float = 180
    # Provider requests that may be in flight at once. Bible scans use this to
    # process several chapters in parallel instead of one after another.
    AI_MAX_CONCURRENT_REQUESTS: int = 3
    AI_SETTINGS_ENCRYPTION_KEY: str | None = None
    COOKIE_SECURE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


# BaseSettings reads required values from the environment and .env at runtime.
# Pylance cannot account for Pydantic's settings sources during constructor analysis.
settings = Settings()  # pyright: ignore[reportCallIssue]
