"""CORS configuration regression tests.

Root cause investigated live against production: Starlette's `CORSMiddleware`
(configured in `app/main.py`) rejects a preflight `OPTIONS` request with
`400 "Disallowed CORS origin"` whenever the request's `Origin` header isn't
in `Settings.cors_origins_list` - which is built ONLY from the `CORS_ORIGINS`
environment variable (`app/core/config.py`). `CORS_ALLOWED_ORIGINS` is not a
field on `Settings` at all (`model_config = SettingsConfigDict(extra="ignore")`)
and is silently discarded if set - a real, previously-seen source of
production drift (see `docker/docker-compose.prod.yml`'s own comments on the
base compose file's dead `CORS_ALLOWED_ORIGINS` key).

`app.main.app` (and `settings`) are module-level singletons built once at
import time, so these tests can't just mutate `os.environ` mid-test and
expect an already-built app's CORS middleware to notice - the middleware's
`allow_origins` list is captured once, synchronously, inside
`add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, ...)`
during `create_app()`. Each test below builds a FRESH app via
`app.main.create_app()` after temporarily mutating the shared `settings`
object's `CORS_ORIGINS`, then immediately restores it - so no test leaks its
CORS configuration into any other test or into the real `app.main.app`
singleton used elsewhere.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app

PROD_ORIGIN = "http://192.168.68.106:3000"


@contextmanager
def _client_with_cors(cors_origins: str) -> Iterator[TestClient]:
    """Builds a fresh app/client with `CORS_ORIGINS` temporarily set to
    `cors_origins`, then restores the shared `settings` singleton
    immediately - the returned client's own CORS middleware already has
    its `allow_origins` baked in by then, so the restore doesn't affect it."""
    original = settings.CORS_ORIGINS
    settings.CORS_ORIGINS = cors_origins
    try:
        test_app = create_app()
    finally:
        settings.CORS_ORIGINS = original
    with TestClient(test_app) as client:
        yield client


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_configured_production_origin_is_allowed() -> None:
    """A: CORS_ORIGINS set to the real production frontend origin - a
    matching preflight succeeds with the exact origin echoed back."""
    with _client_with_cors(PROD_ORIGIN) as client:
        response = _preflight(client, PROD_ORIGIN)
        assert response.status_code == 200, response.text
        assert response.headers["access-control-allow-origin"] == PROD_ORIGIN


def test_unrelated_origin_is_rejected() -> None:
    """B: an origin never listed in CORS_ORIGINS is rejected outright -
    this is the exact production symptom (400, not just missing headers)."""
    with _client_with_cors(PROD_ORIGIN) as client:
        response = _preflight(client, "http://evil.example.com")
        assert response.status_code == 400, response.text
        assert response.text == "Disallowed CORS origin"


def test_localhost_origin_works_when_configured() -> None:
    """C: the dev-facing localhost origin still works when it's actually
    the configured value - this feature isn't Laboratory/production-only,
    it must not regress local development."""
    with _client_with_cors("http://localhost:3000") as client:
        response = _preflight(client, "http://localhost:3000")
        assert response.status_code == 200, response.text
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_successful_preflight_allows_the_real_login_route_to_be_reached() -> None:
    """D: a successful preflight isn't the whole story - the ACTUAL POST
    must reach the auth layer (not get stopped by CORS) once the origin is
    allowed. Sends a deliberately incomplete body (missing `password`) so
    the response comes back as a 422 from Pydantic request validation
    before any database access - proving the request reached the route
    handler's own layer, not a CORS-layer 400."""
    with _client_with_cors(PROD_ORIGIN) as client:
        preflight = _preflight(client, PROD_ORIGIN)
        assert preflight.status_code == 200, preflight.text

        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": PROD_ORIGIN},
            json={"email_or_username": "nobody@example.com"},  # missing required `password`
        )
        assert response.status_code == 422, response.text
        assert response.headers.get("access-control-allow-origin") == PROD_ORIGIN


def test_cors_allowed_origins_dead_variable_has_no_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    """E: `CORS_ALLOWED_ORIGINS` is NOT read by this application at all -
    `Settings` only has a `CORS_ORIGINS` field (`extra="ignore"` silently
    drops anything else). Locks this in as a regression test so the dead
    variable can never be silently reintroduced as if it mattered - if a
    future change actually wires it up, this test's assertion that the
    production origin is still rejected (because ONLY the dead variable was
    set, not CORS_ORIGINS) will start failing, which is the point."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    baseline_cors_origins = Settings().CORS_ORIGINS

    # Direct proof: a freshly-constructed `Settings()` (which DOES read the
    # real process environment, unlike the cached module-level `settings`
    # singleton) still has no idea `CORS_ALLOWED_ORIGINS` exists. Compared
    # against whatever this environment's own baseline is (a local `.env`
    # may override the field's declared default) rather than the bare
    # pydantic field default, since only the ABSENCE of the dead variable's
    # value is what actually matters here.
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", PROD_ORIGIN)
    fresh_settings = Settings()
    assert not hasattr(fresh_settings, "CORS_ALLOWED_ORIGINS")
    assert fresh_settings.CORS_ORIGINS == baseline_cors_origins
    assert PROD_ORIGIN not in fresh_settings.cors_origins_list

    # End-to-end proof: with ONLY the dead variable set (never CORS_ORIGINS),
    # the production origin is still rejected - setting the dead variable
    # changes nothing about real request handling either.
    with _client_with_cors(fresh_settings.CORS_ORIGINS) as client:
        response = _preflight(client, PROD_ORIGIN)
        assert response.status_code == 400, response.text
        assert response.text == "Disallowed CORS origin"
