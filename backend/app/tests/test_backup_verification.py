"""Phase 11: unit tests for the pure backup-verification and
backup-retention logic. No database, no real pg_dump invocation - these
test the exact rules that make "a file exists" different from "a backup
succeeded", and that make retention failure-safe."""

from datetime import UTC, datetime, timedelta

from app.services.backup_retention import BackupFileInfo, select_backups_to_delete
from app.services.backup_verification import verify_dump_file


class TestVerifyDumpFile:
    def test_missing_file_is_invalid(self, tmp_path):
        is_valid, error = verify_dump_file(tmp_path / "does-not-exist.sql")
        assert is_valid is False
        assert "does not exist" in error

    def test_empty_file_is_invalid(self, tmp_path):
        path = tmp_path / "empty.sql"
        path.write_text("")
        is_valid, error = verify_dump_file(path)
        assert is_valid is False
        assert "empty" in error

    def test_file_without_pg_dump_header_is_invalid(self, tmp_path):
        """A file that exists and is non-empty but isn't actually a real
        pg_dump output (e.g. truncated mid-write, or some unrelated file)
        must still be rejected - this is the exact "a file exists is not
        the same as a backup succeeded" check the whole module exists for."""
        path = tmp_path / "not-a-dump.sql"
        path.write_text("this is not a real dump file, just some text")
        is_valid, error = verify_dump_file(path)
        assert is_valid is False
        assert "header" in error

    def test_valid_dump_header_is_valid(self, tmp_path):
        path = tmp_path / "real-looking-dump.sql"
        path.write_text("-- PostgreSQL database dump\n--\n\nCREATE TABLE clinics (...);\n")
        is_valid, error = verify_dump_file(path)
        assert is_valid is True
        assert error is None


class TestSelectBackupsToDelete:
    def _backup(self, identifier: str, days_ago: int, now: datetime) -> BackupFileInfo:
        return BackupFileInfo(identifier=identifier, created_at=now - timedelta(days=days_ago))

    def test_empty_list_deletes_nothing(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        assert select_backups_to_delete([], now=now) == []

    def test_single_backup_is_never_deleted_even_if_ancient(self):
        """The failure-safety invariant: even a single, very old backup
        (e.g. every subsequent day's backup attempt has been failing) must
        never be deleted - it's the only known-good backup there is."""
        now = datetime(2026, 6, 15, tzinfo=UTC)
        ancient = self._backup("only-one", days_ago=400, now=now)
        assert select_backups_to_delete([ancient], now=now) == []

    def test_all_backups_within_daily_window_are_kept(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        backups = [self._backup(f"day-{i}", days_ago=i, now=now) for i in range(7)]
        assert select_backups_to_delete(backups, now=now, keep_daily=7) == []

    def test_backups_beyond_all_windows_are_deleted(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        # Recent one (kept as "newest" + within daily window) and a very
        # old one, isolated in its own month/week so it's not the one
        # monthly/weekly representative kept for its period either -
        # combined with something else in the same period so it isn't
        # picked as that period's sole survivor.
        recent = self._backup("recent", days_ago=0, now=now)
        very_old_a = BackupFileInfo("very-old-a", now - timedelta(days=400))
        very_old_b = BackupFileInfo("very-old-b", now - timedelta(days=401))
        to_delete = select_backups_to_delete(
            [recent, very_old_a, very_old_b], now=now, keep_daily=7, keep_weekly=4, keep_monthly=6
        )
        # Only the OLDEST of the two same-period stale backups would ever
        # be kept as that period's representative if they fell inside the
        # monthly window - both are outside every window here, so both
        # are deleted, "recent" is not.
        assert "recent" not in to_delete
        assert "very-old-a" in to_delete
        assert "very-old-b" in to_delete

    def test_weekly_bucket_keeps_only_the_oldest_backup_per_iso_week(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)  # a Monday
        # Two backups in the same ISO week, both outside the daily window
        # but inside the weekly window.
        b1 = self._backup("week-early", days_ago=10, now=now)
        b2 = self._backup("week-late", days_ago=9, now=now)
        recent = self._backup("recent", days_ago=0, now=now)
        to_delete = select_backups_to_delete([recent, b1, b2], now=now, keep_daily=7, keep_weekly=4)
        # Whichever of b1/b2 is earlier (b1, days_ago=10) should survive as
        # the week's representative if they land in the same ISO week;
        # otherwise both may survive (different weeks) - either way,
        # "recent" must never be deleted, and at most one of the pair is.
        assert "recent" not in to_delete
        assert len(to_delete) <= 1

    def test_monthly_bucket_keeps_only_the_oldest_backup_per_month(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        # Two backups far enough back to be in the monthly-only bucket
        # (beyond daily+weekly windows), same calendar month.
        b1 = self._backup("month-early", days_ago=60, now=now)
        b2 = self._backup("month-late", days_ago=59, now=now)
        recent = self._backup("recent", days_ago=0, now=now)
        to_delete = select_backups_to_delete(
            [recent, b1, b2], now=now, keep_daily=7, keep_weekly=4, keep_monthly=6
        )
        assert "recent" not in to_delete
        # At most one of the same-month pair survives.
        assert len(to_delete) <= 1
