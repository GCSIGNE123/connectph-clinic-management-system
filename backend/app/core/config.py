"""Application configuration loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal

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
    # Single source of truth for the version string shown in `app.main`'s
    # FastAPI `version=`, the `/api/v1/system/status` dashboard field, and
    # `/health`. Kept in sync with the repo-root `VERSION` file,
    # `backend/pyproject.toml`, and `frontend/package.json` (see the
    # version-drift housekeeping note in RELEASE_NOTES.md's RC1 entry).
    APP_VERSION: str = "1.7.0-rc1"

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

    # --- Post-RC1 Phase 2 Milestone 1: Cloud Readiness ---
    # Groundwork/plumbing only - detecting and displaying connectivity state.
    # No business logic currently branches on DEPLOYMENT_MODE; defaults to
    # "local" so every existing deployment that predates this var (i.e. it's
    # absent from the environment entirely) behaves identically to before.
    #   local  - clinic runs fully offline/on-prem, no cloud backend exists.
    #   hybrid - a cloud backend/database is expected to be reachable (future
    #            Milestone 2+ sync work); Milestone 1 only surfaces this as a
    #            label, it does not change behavior.
    DEPLOYMENT_MODE: Literal["local", "hybrid"] = "local"

    # Future cloud backend base URL, used ONLY by the Connectivity Service's
    # own lightweight reachability check (app/services/connectivity_service.py).
    # Optional/nullable - when unset (the realistic day-one state for every
    # existing local clinic), Cloud Server Status reads "Not Configured", not
    # "Down". Not used for any actual request routing or sync in Milestone 1.
    CLOUD_API_URL: str | None = None

    # Placeholder for a future cloud Postgres connection string (Milestone 2
    # / Cloud Backup). NOT connected to or used for anything real yet - do
    # not wire this into any session/engine. Reserved for forward compat.
    CLOUD_DATABASE_URL: str | None = None

    # --- Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync) ---
    # Shared secret for the local sync worker -> cloud backup API channel
    # (`X-Sync-Api-Key` header, checked in `app/api/v1/backup.py`). This is a
    # distinct, service-to-service credential - NOT a clinic-staff JWT, NOT a
    # patient JWT, NOT a platform-admin JWT - consistent with this codebase's
    # existing pattern of structurally distinct auth per principal class.
    # Optional/nullable: unset means the local sync worker has nothing valid
    # to authenticate with, so it simply never succeeds a sync attempt (jobs
    # stay queued and retry) rather than the app failing to start.
    CLOUD_SYNC_API_KEY: str | None = None

    # How often the background sync worker checks the queue, in seconds.
    SYNC_WORKER_INTERVAL_SECONDS: int = 30
    # Retry/backoff bounds for failed sync jobs (exponential: base * 2^retry,
    # capped). Never discards a job - always retried, just further apart.
    SYNC_RETRY_BASE_SECONDS: int = 30
    SYNC_RETRY_MAX_SECONDS: int = 1800  # 30 minutes
    SYNC_HTTP_TIMEOUT_SECONDS: float = 10.0

    # --- Post-RC1 Phase 2.5: Production Cloud Deployment ---
    # Environment-driven CORS/cookie posture only - no new business logic.
    # Production deployments set CORS_ORIGINS to the real domain(s) (e.g.
    # https://clinic.connectph-it.com) instead of the dev-only localhost
    # defaults above. COOKIE_SECURE/COOKIE_SAMESITE (already defined above)
    # should be true/"lax" (or "none" only if the frontend and backend are
    # ever on different top-level domains needing cross-site cookies) behind
    # HTTPS in production; see DEPLOYMENT.md.

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
