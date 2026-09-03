"""Regression test for the receptionist patient-access production incident's
root cause: `COOKIE_SECURE=true` (the correct default for a real HTTPS
deployment) makes browsers refuse to store/send the httpOnly refresh-token
cookie set by `/auth/login` when the server is actually reached over plain
HTTP - exactly what every `DEPLOYMENT_MODE=local` clinic install is (see
docs/LOCAL_DEPLOYMENT.md and `.env.local-production.example`). The symptom is
silent and delayed: login works, then ~ACCESS_TOKEN_EXPIRE_MINUTES later every
authenticated request starts failing ("Not authenticated" on writes, a
silently-empty result on list endpoints that don't check `isError`) because
the automatic token-refresh call has no cookie to send.

`app.main.create_app()` now logs a loud startup warning for exactly this
combination - locked in here the same way `test_cors_configuration.py` locks
in its own `app.main`/`settings` regression (fresh `create_app()` call per
test, `settings` mutated and restored around it so no test leaks its
configuration into another test or into the real `app.main.app` singleton).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from app.core.config import settings
from app.main import create_app


@contextmanager
def _settings_override(**overrides) -> Iterator[None]:
    originals = {key: getattr(settings, key) for key in overrides}
    for key, value in overrides.items():
        setattr(settings, key, value)
    try:
        yield
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)


def test_warns_when_cookie_secure_true_and_deployment_mode_local(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `setup_logging()` (called inside `create_app()`) replaces the root
    # logger's handlers with its own `StreamHandler(sys.stdout)` +
    # `JSONLogFormatter` (see app/main.py) - this REMOVES pytest's `caplog`
    # handler in the process, so the warning must be observed via captured
    # stdout instead of `caplog.records`.
    with _settings_override(DEPLOYMENT_MODE="local", COOKIE_SECURE=True):
        create_app()

    assert "COOKIE_SECURE=true" in capsys.readouterr().out


def test_no_warning_when_cookie_secure_false_and_deployment_mode_local(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The correct local-clinic configuration (per `.env.local-production.example`)
    must stay silent - this warning is not a generic "your config differs
    from the default" nag."""
    with _settings_override(DEPLOYMENT_MODE="local", COOKIE_SECURE=False):
        create_app()

    assert "COOKIE_SECURE=true" not in capsys.readouterr().out


def test_no_warning_when_deployment_mode_is_not_local(capsys: pytest.CaptureFixture[str]) -> None:
    """`COOKIE_SECURE=true` is the CORRECT setting for a real cloud/HTTPS
    deployment (`DEPLOYMENT_MODE=hybrid`) - this warning must only fire for
    the specific local-plain-HTTP combination, not for every non-default
    cookie setting."""
    with _settings_override(DEPLOYMENT_MODE="hybrid", COOKIE_SECURE=True):
        create_app()

    assert "COOKIE_SECURE=true" not in capsys.readouterr().out
