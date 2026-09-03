"""Tests for deployment metadata: `app/core/deploy_info.py`,
`scripts/write_deploy_info.py`, and their exposure via `GET /health` and
`GET /system/status` (see `deploy/windows/update_server.bat` and
`docs/UPDATE_PROCEDURE.md` for the end-to-end mechanism this backs).

Every test monkeypatches the module's file path rather than touching the
real, gitignored `backend/deploy_info.json` - these tests must never depend
on (or leave behind) that file's actual state on the machine running them.
"""

import json
import sys
from pathlib import Path

from httpx import AsyncClient

from app.core import deploy_info as deploy_info_module

# No module-level `pytestmark = pytest.mark.asyncio` here (unlike most other
# test files in this suite) - this file deliberately mixes plain sync tests
# (the pure `get_deploy_info()`/`write_deploy_info.py` unit tests) with async
# ones (the endpoint tests). `asyncio_mode = "auto"` (see backend/pyproject.toml)
# already runs every `async def test_*` correctly with no marker needed, so
# nothing is lost by omitting it - and applying it at module level would
# incorrectly tag the sync tests too.


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    return {"Authorization": f"Bearer {token}"}


# --- app/core/deploy_info.py::get_deploy_info() ---


def test_get_deploy_info_returns_all_none_when_file_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", tmp_path / "deploy_info.json")
    assert deploy_info_module.get_deploy_info() == {
        "git_commit": None, "git_commit_short": None, "deployed_at": None,
    }


def test_get_deploy_info_returns_all_none_on_malformed_json(tmp_path, monkeypatch) -> None:
    path = tmp_path / "deploy_info.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", path)
    assert deploy_info_module.get_deploy_info() == {
        "git_commit": None, "git_commit_short": None, "deployed_at": None,
    }


def test_get_deploy_info_parses_a_real_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "deploy_info.json"
    path.write_text(
        json.dumps({
            "git_commit": "abc1234def", "git_commit_short": "abc1234",
            "deployed_at": "2026-09-04T00:00:00+00:00",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", path)
    assert deploy_info_module.get_deploy_info() == {
        "git_commit": "abc1234def", "git_commit_short": "abc1234",
        "deployed_at": "2026-09-04T00:00:00+00:00",
    }


# --- scripts/write_deploy_info.py ---


def _import_write_deploy_info():
    """Imports the standalone script as a module - it lives outside `app/`
    (matching `backup_and_prune.py`/`verify_restore.py`'s own convention of
    not being an installed package member), so it's loaded directly by path
    rather than via a normal package import."""
    import importlib.util

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "write_deploy_info.py"
    spec = importlib.util.spec_from_file_location("write_deploy_info", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_write_deploy_info_writes_commit_and_short_sha_and_timestamp(tmp_path, monkeypatch) -> None:
    write_deploy_info = _import_write_deploy_info()
    output_path = tmp_path / "deploy_info.json"
    monkeypatch.setattr(write_deploy_info, "_OUTPUT_PATH", output_path)
    commit_sha = "710c49ee670eb5bd8fd7fc9afe747b51e6a23960"
    monkeypatch.setattr(sys, "argv", ["write_deploy_info.py", "--commit", commit_sha])

    exit_code = write_deploy_info.main()

    assert exit_code == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["git_commit"] == commit_sha
    assert written["git_commit_short"] == "710c49e"
    assert written["deployed_at"]  # a real ISO timestamp was written, not fabricated ahead of time


def test_write_deploy_info_rejects_a_value_that_is_not_a_commit_sha(tmp_path, monkeypatch) -> None:
    write_deploy_info = _import_write_deploy_info()
    output_path = tmp_path / "deploy_info.json"
    monkeypatch.setattr(write_deploy_info, "_OUTPUT_PATH", output_path)
    monkeypatch.setattr(sys, "argv", ["write_deploy_info.py", "--commit", "not-a-real-sha!!"])

    exit_code = write_deploy_info.main()

    assert exit_code == 1
    assert not output_path.exists()


# --- GET /health ---


async def test_health_endpoint_reports_null_deploy_info_when_file_absent(
    client: AsyncClient, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", tmp_path / "deploy_info.json")
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["git_commit"] is None
    assert body["deployed_at"] is None


async def test_health_endpoint_reports_the_deployed_commit_when_present(
    client: AsyncClient, tmp_path, monkeypatch
) -> None:
    path = tmp_path / "deploy_info.json"
    path.write_text(
        json.dumps({
            "git_commit": "cafef00d" * 5, "git_commit_short": "cafef00",
            "deployed_at": "2026-09-04T12:00:00+00:00",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", path)

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["git_commit"] == "cafef00d" * 5
    assert body["git_commit_short"] == "cafef00"
    assert body["deployed_at"] == "2026-09-04T12:00:00+00:00"


# --- GET /system/status ---


async def test_system_status_reports_deploy_info_fields(
    client: AsyncClient, make_clinic_with_owner, tmp_path, monkeypatch
) -> None:
    path = tmp_path / "deploy_info.json"
    path.write_text(
        json.dumps({
            "git_commit": "deadbeef" * 5, "git_commit_short": "deadbee",
            "deployed_at": "2026-09-04T09:30:00+00:00",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", path)
    headers = await _owner_headers(client, make_clinic_with_owner)

    response = await client.get("/api/v1/system/status", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["git_commit"] == "deadbeef" * 5
    assert body["git_commit_short"] == "deadbee"
    assert body["deployed_at"] == "2026-09-04T09:30:00+00:00"


async def test_system_status_reports_null_deploy_info_on_a_never_deployed_machine(
    client: AsyncClient, make_clinic_with_owner, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(deploy_info_module, "_DEPLOY_INFO_PATH", tmp_path / "deploy_info.json")
    headers = await _owner_headers(client, make_clinic_with_owner)

    response = await client.get("/api/v1/system/status", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["git_commit"] is None
    assert body["git_commit_short"] is None
    assert body["deployed_at"] is None
