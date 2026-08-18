"""Phase 5B (P2, LR4): /docs, /redoc, /openapi.json must not be publicly
exposed in production - previously always enabled regardless of ENV,
revealing the full API surface (including internal/admin routes).
Development/test behavior must stay unchanged."""

from app.core.config import settings
from app.main import create_app


def test_docs_disabled_when_env_is_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENV", "production")
    prod_app = create_app()
    assert prod_app.docs_url is None
    assert prod_app.redoc_url is None
    assert prod_app.openapi_url is None


def test_docs_enabled_when_env_is_development() -> None:
    from app.main import app as dev_app

    assert dev_app.docs_url == "/docs"
    assert dev_app.redoc_url == "/redoc"
    assert dev_app.openapi_url == "/openapi.json"
