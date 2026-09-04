"""Tests for `scripts/backup_docker.py` - the Docker-native backup used as
the mandatory pre-migration step by the repo-root `deploy.cmd` (see
`docs/DOCKER_UPDATE_PROCEDURE.md`). Every `docker`/`docker exec` call is
mocked via a fake `subprocess.run` - these tests must never require a real
Docker daemon or a real Postgres container.
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _import_backup_docker():
    """Loads the standalone script by path - it lives outside `app/`,
    matching `backup_and_prune.py`/`write_deploy_info.py`'s own convention."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "backup_docker.py"
    spec = importlib.util.spec_from_file_location("backup_docker", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["backup_docker"] = module
    spec.loader.exec_module(module)
    return module


DUMP_HEADER = "-- PostgreSQL database dump\n-- Dumped from a fake test fixture\n"


@pytest.fixture
def backup_docker():
    return _import_backup_docker()


def test_container_not_running_fails_without_attempting_a_dump(
    tmp_path, monkeypatch, backup_docker
):
    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["docker", "inspect"]
        return SimpleNamespace(returncode=0, stdout="false\n", stderr="")

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 1
    assert list(tmp_path.glob("*.sql")) == []  # no dump file was ever created
    log_text = (tmp_path / backup_docker.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "FAILED" in log_text
    assert "not running" in log_text


def test_docker_cli_missing_fails_clearly(tmp_path, monkeypatch, backup_docker):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 1
    log_text = (tmp_path / backup_docker.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "not on PATH" in log_text


def test_pg_dump_failure_inside_container_fails_and_leaves_no_valid_backup(
    tmp_path, monkeypatch, backup_docker
):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        # docker exec pg_dump - simulate a real failure (e.g. bad credentials)
        stdout = kwargs.get("stdout")
        if stdout is not None:
            stdout.write(b"")
        return SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"pg_dump: error: connection failed"
        )

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 1
    log_text = (tmp_path / backup_docker.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "FAILED" in log_text
    assert "connection failed" in log_text


def test_successful_backup_is_verified_and_logged(tmp_path, monkeypatch, backup_docker):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        # docker exec pg_dump - write a realistic-looking dump to the
        # caller's `stdout=` file handle, exactly like a real subprocess would.
        stdout = kwargs.get("stdout")
        assert stdout is not None
        stdout.write(DUMP_HEADER.encode("utf-8"))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 0
    dumps = list(tmp_path.glob("docker-backup-*.sql"))
    assert len(dumps) == 1
    assert dumps[0].read_text(encoding="utf-8") == DUMP_HEADER
    log_text = (tmp_path / backup_docker.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "SUCCESS" in log_text
    assert "verified" in log_text


def test_empty_dump_file_fails_verification(tmp_path, monkeypatch, backup_docker):
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        # exits 0 but writes nothing - e.g. a silently misconfigured db name
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 1
    log_text = (tmp_path / backup_docker.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "FAILED" in log_text
    assert "empty" in log_text.lower()


def test_only_docker_backup_prefixed_files_are_subject_to_retention(
    tmp_path, monkeypatch, backup_docker
):
    """A file left behind by the OTHER (NSSM) backup script
    (`scheduled-backup-*.sql`) must never be touched by this script's
    retention pass - each mechanism only manages its own family."""
    other_mechanisms_file = tmp_path / "scheduled-backup-20200101T000000.sql"
    other_mechanisms_file.write_text(DUMP_HEADER, encoding="utf-8")

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        stdout = kwargs.get("stdout")
        stdout.write(DUMP_HEADER.encode("utf-8"))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backup_docker.subprocess, "run", fake_run)

    exit_code = backup_docker.run(
        backup_dir=tmp_path, container="connectph-postgres", db_user="connectph",
        db_name="canora_clinic", keep_daily=7, keep_weekly=4, keep_monthly=6,
    )

    assert exit_code == 0
    assert other_mechanisms_file.exists()  # untouched by this run's retention


def test_main_uses_expected_defaults(monkeypatch, backup_docker):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(backup_docker, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["backup_docker.py"])

    exit_code = backup_docker.main()

    assert exit_code == 0
    assert captured["container"] == backup_docker.DEFAULT_CONTAINER == "connectph-postgres"
    assert captured["db_user"] == backup_docker.DEFAULT_DB_USER == "connectph"
    assert captured["db_name"] == backup_docker.DEFAULT_DB_NAME == "canora_clinic"


def test_main_accepts_overrides(monkeypatch, backup_docker):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(backup_docker, "run", fake_run)
    monkeypatch.setattr(
        sys, "argv",
        [
            "backup_docker.py", "--container", "other-postgres",
            "--db-user", "other_user", "--db-name", "other_db",
        ],
    )

    backup_docker.main()

    assert captured["container"] == "other-postgres"
    assert captured["db_user"] == "other_user"
    assert captured["db_name"] == "other_db"
