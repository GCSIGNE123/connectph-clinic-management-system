"""Phase 11: unit tests for the filesystem-only helper functions in
`scripts/backup_and_prune.py` (filename parsing for retention, and the
best-effort attachment-directory copy) - no Postgres/subprocess needed,
imported directly from its file path since `scripts/` isn't a package."""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "backup_and_prune.py"
_spec = importlib.util.spec_from_file_location("backup_and_prune", _SCRIPT_PATH)
backup_and_prune = importlib.util.module_from_spec(_spec)
sys.modules["backup_and_prune"] = backup_and_prune
_spec.loader.exec_module(backup_and_prune)


class TestExistingBackups:
    def test_parses_well_formed_scheduled_backup_filenames(self, tmp_path):
        (tmp_path / "scheduled-backup-20260101T020000.sql").write_text("-- PostgreSQL database dump\n")
        (tmp_path / "scheduled-backup-20260102T020000.sql").write_text("-- PostgreSQL database dump\n")
        infos = backup_and_prune._existing_backups(tmp_path)
        assert len(infos) == 2
        assert {i.created_at.strftime("%Y%m%d") for i in infos} == {"20260101", "20260102"}

    def test_ignores_files_that_do_not_match_the_naming_convention(self, tmp_path):
        """A manually-triggered backup (different filename shape, from
        `BackupService`) or any unrelated file in the same directory must
        never be picked up by retention - only files this script itself
        created are candidates for deletion."""
        (tmp_path / "backup-20260101T020000-abc123.sql").write_text("-- PostgreSQL database dump\n")
        (tmp_path / "readme.txt").write_text("not a backup")
        infos = backup_and_prune._existing_backups(tmp_path)
        assert infos == []


class TestCopyAttachmentDirs:
    def test_copies_existing_attachment_directories(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        (repo_root / "backend" / "var" / "laboratory_attachments" / "clinic-1").mkdir(parents=True)
        (repo_root / "backend" / "var" / "laboratory_attachments" / "clinic-1" / "file.jpg").write_text("fake image bytes")
        monkeypatch.setattr(backup_and_prune, "_REPO_ROOT", repo_root)

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        log_path = backup_dir / "backup_log.txt"
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        backup_and_prune._copy_attachment_dirs(backup_dir, log_path, started_at)

        copied = backup_dir / "attachments-20260101T000000" / "laboratory_attachments" / "clinic-1" / "file.jpg"
        assert copied.exists()
        assert copied.read_text() == "fake image bytes"

    def test_no_attachment_directories_present_is_not_an_error(self, tmp_path, monkeypatch):
        """A fresh install with zero uploaded attachments yet must not
        produce a warning/failure - nothing to copy is not an error."""
        repo_root = tmp_path / "repo"
        (repo_root / "backend").mkdir(parents=True)
        monkeypatch.setattr(backup_and_prune, "_REPO_ROOT", repo_root)

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        log_path = backup_dir / "backup_log.txt"

        backup_and_prune._copy_attachment_dirs(backup_dir, log_path, datetime(2026, 1, 1, tzinfo=UTC))

        assert list(backup_dir.glob("attachments-*")) == []


class TestRunDestinationUnavailable:
    """Phase 12: an unusable backup destination (unmounted drive, permission
    denied, or a regular file blocking the path) must fail cleanly through
    run()'s own return code, not surface as an unhandled traceback - this is
    the difference between "the scheduled task shows a failure" and "the
    scheduled task's own runner crashes", which is much harder for a
    non-technical clinic operator to notice and report."""

    def test_destination_path_blocked_by_an_existing_file_fails_cleanly(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")

        exit_code = backup_and_prune.run(
            backup_dir=blocker, keep_daily=7, keep_weekly=4, keep_monthly=6
        )

        assert exit_code == 1
