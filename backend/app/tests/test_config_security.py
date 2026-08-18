"""Phase 5B (P1, D3): production must never boot with the publicly-known
default JWT signing secret. Constructs `Settings` directly (not via the
cached global `settings`) so this test doesn't need to mutate real process
env vars or touch the module-level singleton."""

import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_DEFAULT_JWT_SECRET_KEY, Settings


def test_production_with_default_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="insecure default"):
        Settings(ENV="production", JWT_SECRET_KEY=INSECURE_DEFAULT_JWT_SECRET_KEY)


def test_production_with_a_real_custom_secret_is_accepted() -> None:
    settings = Settings(ENV="production", JWT_SECRET_KEY="a-real-randomly-generated-secret-value")
    assert settings.ENV == "production"


def test_development_with_default_secret_is_still_accepted() -> None:
    """Existing development/test behavior is unaffected - only ENV ==
    "production" triggers the check."""
    settings = Settings(ENV="development", JWT_SECRET_KEY=INSECURE_DEFAULT_JWT_SECRET_KEY)
    assert settings.JWT_SECRET_KEY == INSECURE_DEFAULT_JWT_SECRET_KEY


def test_test_environment_with_default_secret_is_still_accepted() -> None:
    settings = Settings(ENV="test", JWT_SECRET_KEY=INSECURE_DEFAULT_JWT_SECRET_KEY)
    assert settings.JWT_SECRET_KEY == INSECURE_DEFAULT_JWT_SECRET_KEY
