"""FastAPI application factory and entrypoint for CONNECT.PH Clinic Platform."""

import logging
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.services import connectivity_service, medicine_expiry_service, sync_worker_service


class JSONLogFormatter(logging.Formatter):
    """Minimal structured (JSON-ish) log line formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras: Mapping[str, object] = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "taskName",
            )
        }
        payload.update(extras)
        return str(payload)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO if settings.ENV != "development" else logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Post-RC1 Phase 2 Milestone 1: Cloud Readiness - starts the
    # Connectivity Service's periodic background poll (every
    # CHECK_INTERVAL_SECONDS). Purely additive: detects/displays
    # connectivity state only, never gates any business logic.
    connectivity_service.start_background_loop()
    # Post-RC1 Phase 2 Milestone 2: Cloud Backup - starts the background
    # sync worker (drains `sync_jobs` against the cloud Backup API every
    # `SYNC_WORKER_INTERVAL_SECONDS`). Purely additive/best-effort: in
    # `DEPLOYMENT_MODE=local` (CLOUD_API_URL unset), it runs but is always a
    # no-op - see sync_worker_service.py's module docstring.
    sync_worker_service.start_background_loop()
    # Medicine Inventory Phase 3: hourly poll, internally guarded to run at
    # most once per (UTC) day per clinic - see medicine_expiry_service.py's
    # module docstring for the full concurrency/idempotency design.
    medicine_expiry_service.start_background_loop()
    try:
        yield
    finally:
        medicine_expiry_service.stop_background_loop()
        sync_worker_service.stop_background_loop()
        connectivity_service.stop_background_loop()


def create_app() -> FastAPI:
    setup_logging()

    # Local-clinic-deployment footgun check: `COOKIE_SECURE=true` (the
    # correct default for a real HTTPS deployment) makes the browser refuse
    # to ever store/send the refresh-token cookie set by `/auth/login` when
    # this server is actually reached over plain HTTP - which every
    # `DEPLOYMENT_MODE=local` install is, by design (see
    # docs/LOCAL_DEPLOYMENT.md and `.env.local-production.example`'s own
    # "COOKIE_SECURE must be false here" comment). The symptom is silent and
    # delayed: login works, then ~ACCESS_TOKEN_EXPIRE_MINUTES later every
    # authenticated request starts failing with "Not authenticated" (list
    # endpoints often masking this as an empty result instead of a visible
    # error) because the automatic token-refresh call has no cookie to send.
    # This is exactly the failure mode investigated for the receptionist
    # patient-access incident - logging it loudly at startup turns a
    # confusing, hours-later support case into an immediate, obvious fix.
    if settings.DEPLOYMENT_MODE == "local" and settings.COOKIE_SECURE:
        logging.getLogger("app.startup").warning(
            "COOKIE_SECURE=true with DEPLOYMENT_MODE=local: the refresh-token "
            "cookie will be silently dropped by browsers unless this server is "
            "served over HTTPS. A local clinic install (plain HTTP) needs "
            "COOKIE_SECURE=false in its .env - see docs/LOCAL_DEPLOYMENT.md."
        )

    # Phase 5B (P2, LR4): Swagger/ReDoc/OpenAPI schema are disabled in
    # production - they were previously exposed unconditionally, publicly
    # revealing the full API surface (including internal/admin routes).
    # Development/test behavior is unchanged (docs stay available).
    docs_enabled = settings.ENV != "production"
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Multi-tenant Medical Clinic Management SaaS - backend foundation.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TenantContextMiddleware)

    # Standardized error envelope (Phase 16): every error response - whether
    # raised as an HTTPException, a validation error, or an unhandled
    # exception - is `{"detail": ..., "request_id": "<uuid>"}`. `detail` was
    # already consistent (FastAPI's own default shape, and the only shape
    # used anywhere in this codebase's ~40 route modules per a grep of
    # `HTTPException(` call sites), so the actual gap closed here is adding
    # `request_id` everywhere so a client-reported error can be matched to
    # the exact server-side log line via the same id returned in the
    # `X-Request-ID` response header. See docs/API.md for the full contract.
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": getattr(request.state, "request_id", None)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": jsonable_encoder(exc.errors()),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logging.getLogger("app.error").exception(
            "Unhandled exception", extra={"path": request.url.path, "request_id": request_id}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Post-RC1 (50/50 Queue + Information/Advertisement Panel): serves the
    # real, locally-stored TV Info Panel images written by
    # `POST /tv-info-content/{id}/image` (see `app/api/v1/tv_display.py`'s
    # module docstring) - deliberately not a presigned-URL stub like every
    # other upload flow in this app, since the TV Display must keep working
    # fully offline. Unauthenticated by design, same as the public TV
    # display endpoint itself: these are clinic-facing marketing/info
    # images meant to be shown on an unauthenticated public TV, never
    # sensitive data. Mounted at app-creation time (not lazily) so the
    # directory always exists before the first request.
    tv_info_content_media_root = Path(__file__).resolve().parent.parent / "var" / "tv_info_content_images"
    tv_info_content_media_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/tv-info-content",
        StaticFiles(directory=tv_info_content_media_root),
        name="tv-info-content-media",
    )

    # Round 7 (clinic logo branding): same reasoning/convention as the
    # tv-info-content mount just above - the clinic logo is written by
    # `POST /clinic-settings/logo` (see `app/api/v1/clinic_settings.py`)
    # and must be servable with zero auth, since it also renders on the
    # fully public TV Display kiosk (`GET /public/tv-display/{slug}`), not
    # just the authenticated Clinic Settings/Laboratory Report pages.
    clinic_logo_media_root = Path(__file__).resolve().parent.parent / "var" / "clinic_logo_images"
    clinic_logo_media_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/media/clinic-logo",
        StaticFiles(directory=clinic_logo_media_root),
        name="clinic-logo-media",
    )

    return app


app = create_app()
