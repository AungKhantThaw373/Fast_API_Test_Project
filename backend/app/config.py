from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRETS = {"change-me", "secret", "changeme", "password", "test"}
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    APP_ENV: Literal["development", "production"] = "development"

    user: str
    password: str
    host: str
    port: int
    dbname: str
    DATABASE_SSL: str = "disable"
    JWT_SECRET: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14
    JWT_ISSUER: str = "stillroom"
    JWT_AUDIENCE: str = "stillroom-api"
    FRONTEND_URL: str = "http://localhost:3000"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "stillroom@localhost"
    SMTP_STARTTLS: bool = True

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_CHAT_MODEL: str = "qwen3:4b-instruct"
    OLLAMA_DEEP_MODEL: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    OLLAMA_KEEP_ALIVE: str = "30m"
    OLLAMA_NUM_CTX: int = Field(default=8192, ge=1024, le=131072)
    OLLAMA_NUM_PREDICT: int = Field(default=1200, ge=128, le=8192)
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
    AI_MAX_CONCURRENT_REQUESTS: int = Field(default=3, ge=1, le=16)
    AI_SETTINGS_ENCRYPTION_KEY: str | None = None
    COOKIE_SECURE: bool = False
    # Comma-separated browser origins allowed to call cookie-authenticated
    # endpoints. Both localhost spellings are accepted by default.
    FRONTEND_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Optional comma-separated hostnames for custom provider URLs. Empty means
    # any public host is accepted. Useful for a locked-down deployment.
    PROVIDER_HOST_ALLOWLIST: str = ""
    USER_STORAGE_QUOTA_BYTES: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    USER_FILE_LIMIT: int = Field(default=500, ge=1)
    # Soft warning only; the manual says not to hard-block normal manuscripts.
    STORY_CHAPTER_WARNING: int = Field(default=1000, ge=1)
    # Slow SQL is logged at WARNING; the request id comes from the logging filter.
    SLOW_QUERY_MS: int = Field(default=500, ge=1)
    # Relative paths are resolved from the repository root by the diagnostics route.
    BACKUP_DIR: str = "backups"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def frontend_origins(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.FRONTEND_ORIGINS.split(",") if item.strip()]

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        value = value.strip()
        if len(value) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if value.casefold() in INSECURE_JWT_SECRETS:
            raise ValueError("JWT_SECRET is a well-known placeholder; replace it with a random secret.")
        return value

    @field_validator("AI_SETTINGS_ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        value = value.strip()
        if len(value) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"AI_SETTINGS_ENCRYPTION_KEY must be at least {MIN_SECRET_LENGTH} characters when set."
            )
        return value

    @field_validator("host", "dbname", "user", "password")
    @classmethod
    def validate_database_field(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Database connection settings cannot be empty.")
        return value

    @field_validator("OLLAMA_BASE_URL", "OPENROUTER_BASE_URL")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("Provider base URLs must start with http:// or https://.")
        return value

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.APP_ENV == "production" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when APP_ENV=production.")
        return self


def _load_settings() -> Settings:
    """Load settings, turning validation failures into a readable message.

    A bad .env should not greet the operator with a Pydantic traceback.
    """
    try:
        return Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "<settings>"
            problems.append(f"  - {location}: {error['msg']}")
        raise SystemExit("Configuration error:\n" + "\n".join(problems)) from None


settings = _load_settings()
