"""Tests for the /health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Deployment metadata (see app/core/deploy_info.py) - None in the test
    # environment, since no update_server.bat run has ever written
    # deploy_info.json here; the keys must still be present.
    assert body["git_commit"] is None
    assert body["git_commit_short"] is None
    assert body["deployed_at"] is None
