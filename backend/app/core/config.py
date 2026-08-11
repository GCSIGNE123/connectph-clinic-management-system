"""Application configuration loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All values can be overridden via environment variables or a `.env` file
    at the project root (see `.env.example`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    ENV: str = "development"
    APP_NAME: str = "CONNECT.PH Clinic Platform"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://clinic_user:clinic_password@localhost:5432/connectph_clinic"

    # --- JWT / Auth ---
    JWT_SECRET_KEY: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER_ME: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24

    # --- Account lockout ---
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # --- Cookies ---
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 10
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 60
    RATE_LIMIT_FORGOT_PASSWORD_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_FORGOT_PASSWORD_WINDOW_SECONDS: int = 300
    # Post-RC1 (short TV display URL): the public TV endpoint now also
    # accepts a short, admin-chosen `short_code` alias (e.g. "canora")
    # alongside the existing 192-bit `public_slug` - see
    # `models/tv_display_config.py`'s docstring. A short code is inherently
    # far more guessable than the slug, so this throttles the endpoint per
    # client IP to blunt brute-force enumeration. Generous enough that a
    # real TV's 30s poll + WebSocket-reconnect-with-backoff never trips it.
    RATE_LIMIT_TV_PUBLIC_MAX_ATTEMPTS: int = 60
    RATE_LIMIT_TV_PUBLIC_WINDOW_SECONDS: int = 60

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- SMTP ---
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "no-reply@connect.ph"
    SMTP_PASSWORD: str = "change-me"
    SMTP_FROM: str = "no-reply@connect.ph"

    # --- Supabase ---
    SUPABASE_URL: str = "https://your-project.supabase.co"
    SUPABASE_KEY: str = "your-supabase-service-key"
    SUPABASE_STORAGE_BUCKET: str = "clinic-documents"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
