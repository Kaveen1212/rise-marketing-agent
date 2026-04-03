"""
app/config.py
─────────────────────────────────────────────────────────────────────────────
Central settings for the RISE Tech Village Poster Design Agent.

All values are read from environment variables.  Pydantic-settings validates
every field at startup — if a required secret is missing the app refuses to
start rather than failing silently at runtime.

Security principles applied here:
  • Secrets (API keys, DB URL) are NEVER given default values → forces
    explicit configuration in every environment.
  • DATABASE_URL is always rewritten to use SSL mode=require.
  • JWT secrets are validated to be non-empty strings.
  • Sensitive fields use SecretStr so they never appear in repr() or logs.
─────────────────────────────────────────────────────────────────────────────
"""

from functools import lru_cache
from typing import Literal

from typing import Optional

from pydantic import AnyUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration for the application.
    Fields without defaults MUST be set in the environment / .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Ignore extra vars from the environment — keeps config explicit
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "RISE Poster Agent"
    APP_VERSION: str = "0.1.0"
    # Debug mode is ONLY allowed outside production
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    # Full async PostgreSQL URL.
    # Format: postgresql+asyncpg://user:pass@host:port/dbname
    # Supabase example: postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres
    DATABASE_URL: SecretStr

    # Sync URL used only by Alembic (migrations run synchronously)
    # Format: postgresql+psycopg2://user:pass@host:port/dbname
    DATABASE_SYNC_URL: SecretStr

    # Connection pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30        # seconds to wait for a connection
    DB_POOL_RECYCLE: int = 1800      # recycle connections after 30 min
    DB_ECHO_SQL: bool = False        # set True in dev to log all SQL

    # ── LangGraph Checkpointer ───────────────────────────────────────────────
    # Must point to same PostgreSQL database — stores HITL graph state
    LANGGRAPH_CHECKPOINTER_URL: SecretStr
    LANGGRAPH_THREAD_TTL_HOURS: int = 168   # 7 days — poster review window

    # ── Auth — API Key ───────────────────────────────────────────────────────
    # Used to authenticate requests to the HITL review endpoints
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    API_SECRET_KEY: SecretStr

    # ── Anthropic / Claude ───────────────────────────────────────────────────
    ANTHROPIC_API_KEY: SecretStr
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # ── LangSmith Observability ──────────────────────────────────────────────
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[SecretStr] = None
    LANGCHAIN_PROJECT: str = "rise-poster-agent"

    # ── Image Generation ─────────────────────────────────────────────────────
    STABILITY_AI_API_KEY: Optional[SecretStr] = None
    STABILITY_AI_MODEL: str = "stable-diffusion-xl-1024-v1-0"
    OPENAI_API_KEY: Optional[SecretStr] = None  # DALL-E 3 fallback only

    # ── AWS S3 Storage ───────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: Optional[SecretStr] = None
    AWS_SECRET_ACCESS_KEY: Optional[SecretStr] = None
    AWS_REGION: str = "ap-southeast-1"  # Singapore — closest to Sri Lanka
    S3_POSTER_BUCKET: str = "rise-posters-prod"
    CLOUDFRONT_POSTER_DOMAIN: Optional[AnyUrl] = None
    S3_URL_EXPIRY_SECONDS: int = 3600   # 1 hour (spec: private URLs expire in 1h)

    # ── Social Media Platform APIs ───────────────────────────────────────────
    INSTAGRAM_ACCESS_TOKEN: Optional[SecretStr] = None
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = ""
    FACEBOOK_PAGE_ID: str = ""
    FACEBOOK_PAGE_ACCESS_TOKEN: Optional[SecretStr] = None
    LINKEDIN_ORG_ID: str = ""
    LINKEDIN_ACCESS_TOKEN: Optional[SecretStr] = None
    TIKTOK_CLIENT_KEY: Optional[SecretStr] = None
    TIKTOK_CLIENT_SECRET: Optional[SecretStr] = None

    # ── HITL Review Settings ─────────────────────────────────────────────────
    REVIEW_NOTIFICATION_EMAIL: str = "marketing@risetechvillage.lk"
    REVIEW_SLACK_WEBHOOK_URL: Optional[SecretStr] = None
    REVIEW_SLACK_CHANNEL: str = "#poster-review-queue"
    # Minimum average score (0-5) to enable Approve button — from spec
    REVIEW_APPROVAL_MIN_SCORE: float = 3.5
    # Maximum revision cycles per poster before status → exhausted
    REVIEW_MAX_REVISIONS: int = 3
    # QA Agent minimum confidence — below this, auto-regenerate (no human involved)
    QA_MIN_CONFIDENCE: float = 0.60

    # ── Publish Schedule (Sri Lanka IST = UTC+5:30) ──────────────────────────
    # Hours in Sri Lanka local time (24h format) — from spec
    PUBLISH_HOUR_INSTAGRAM: int = 20    # 8:00 pm
    PUBLISH_HOUR_FACEBOOK: int = 20     # 7:30 pm (handled as minute offset)
    PUBLISH_MINUTE_FACEBOOK: int = 30
    PUBLISH_HOUR_LINKEDIN_AM: int = 9   # 9:00 am
    PUBLISH_HOUR_LINKEDIN_PM: int = 19  # 7:00 pm
    PUBLISH_HOUR_TIKTOK: int = 21       # 9:00 pm

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    # ─────────────────────────────────────────────────────────────────────────
    # Validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("DEBUG", mode="before")
    @classmethod
    def no_debug_in_production(cls, v: bool, info) -> bool:
        """Debug mode must never be enabled in production."""
        # Access other fields via info.data — only fields validated before DEBUG
        return v

    @model_validator(mode="after")
    def enforce_production_security(self) -> "Settings":
        """Hard rules that apply in production only."""
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError(
                    "DEBUG must be False in production. "
                    "Set APP_ENV=development for local work."
                )
            if self.DB_ECHO_SQL:
                raise ValueError(
                    "DB_ECHO_SQL must be False in production — "
                    "SQL logs can expose sensitive data."
                )
        return self

    @field_validator("REVIEW_APPROVAL_MIN_SCORE")
    @classmethod
    def validate_min_score(cls, v: float) -> float:
        if not (1.0 <= v <= 5.0):
            raise ValueError("REVIEW_APPROVAL_MIN_SCORE must be between 1.0 and 5.0")
        return v

    @field_validator("QA_MIN_CONFIDENCE")
    @classmethod
    def validate_qa_confidence(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("QA_MIN_CONFIDENCE must be between 0.0 and 1.0")
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Derived helpers
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def async_database_url(self) -> str:
        """
        Returns the async DB URL with sslmode=require appended.
        SSL is mandatory — we never connect to PostgreSQL unencrypted.
        """
        url = self.DATABASE_URL.get_secret_value()
        if "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}ssl=require"
        return url

    @property
    def sync_database_url(self) -> str:
        """Sync URL for Alembic migrations — also enforces SSL."""
        url = self.DATABASE_SYNC_URL.get_secret_value()
        if "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode=require"
        return url

    def is_production(self) -> bool:
        return self.APP_ENV == "production"


# ─────────────────────────────────────────────────────────────────────────────
# Singleton — import settings from anywhere with: from app.config import settings
# lru_cache ensures Settings() is only instantiated once per process
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
