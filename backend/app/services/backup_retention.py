"""Phase 11: pure backup-retention selection logic.

A simple Grandfather-Father-Son (daily/weekly/monthly) policy, appropriate
for a single-clinic installation generating at most one backup per day:

- Every backup within `keep_daily` days of `now` is kept (recent daily
  granularity - the window you'd actually restore from for "yesterday's
  mistake").
- Older than that but within `keep_weekly` weeks: only the OLDEST backup
  of each ISO calendar week is kept (a weekly snapshot).
- Older than that but within `keep_monthly` months: only the OLDEST
  backup of each calendar month is kept (a monthly snapshot).
- Anything older than `keep_monthly` months, or not selected by the rules
  above, is deleted.

Defaults (7 daily / 4 weekly / 6 monthly) are a starting recommendation
for a single clinic, not a hard requirement - see docs/BACKUP.md for the
reasoning; callers can override.

Deliberately a pure function over `(id, timestamp)` pairs, no filesystem
I/O - the caller (the standalone scheduled script) is responsible for
actually deleting the files this returns, and for the one invariant this
module itself enforces structurally: it is IMPOSSIBLE for this function to
select the single most recent backup for deletion, even when called with
an otherwise-empty or all-old list - see `_keep_ids`'s explicit inclusion
of the newest backup regardless of which bucket it would otherwise fall
into. This is what makes retention failure-safe: a bad/failed run today
never removes yesterday's last known-good backup along with everything
else."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class BackupFileInfo:
    identifier: str
    created_at: datetime


def select_backups_to_delete(
    backups: list[BackupFileInfo],
    *,
    now: datetime,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
) -> list[str]:
    """Returns the `identifier`s of backups that retention should delete.
    Never includes the single most recent backup, even if `backups` is
    otherwise empty of anything else worth keeping."""
    if not backups:
        return []

    ordered = sorted(backups, key=lambda b: b.created_at, reverse=True)
    newest = ordered[0]

    daily_cutoff = now - timedelta(days=keep_daily)
    weekly_cutoff = now - timedelta(weeks=keep_weekly) - timedelta(days=keep_daily)
    monthly_cutoff = weekly_cutoff - timedelta(days=30 * keep_monthly)

    keep_ids: set[str] = {newest.identifier}
    seen_weeks: set[tuple[int, int]] = set()
    seen_months: set[tuple[int, int]] = set()

    # Process oldest-first within each bucket so "the oldest backup of the
    # week/month" is genuinely the one kept, matching a real GFS policy
    # (the earliest snapshot of a period, not the latest).
    for backup in sorted(backups, key=lambda b: b.created_at):
        if backup.created_at >= daily_cutoff:
            keep_ids.add(backup.identifier)
        elif backup.created_at >= weekly_cutoff:
            week_key = backup.created_at.isocalendar()[:2]  # (iso_year, iso_week)
            if week_key not in seen_weeks:
                seen_weeks.add(week_key)
                keep_ids.add(backup.identifier)
        elif backup.created_at >= monthly_cutoff:
            month_key = (backup.created_at.year, backup.created_at.month)
            if month_key not in seen_months:
                seen_months.add(month_key)
                keep_ids.add(backup.identifier)
        # Older than monthly_cutoff: not added to keep_ids -> deleted,
        # unless it happens to be `newest` (impossible here since newest
        # is the most recent, but kept as an explicit invariant via the
        # initial keep_ids seed above, not by luck of iteration order).

    return [b.identifier for b in backups if b.identifier not in keep_ids]
