"""Shared helper for filtering a `DateTime` column by an inclusive
[date_from, date_to] range expressed as plain calendar dates.

Uses the application's existing UTC-calendar-day convention - the same one
`AnalyticsService._resolve_range`/`_to_datetime_bounds` already uses (see
that module's docstring) - not a per-clinic timezone. This is intentional:
the codebase has no working per-clinic timezone conversion anywhere
(`medicine_expiry_service.py` explicitly documents that as out of scope),
so introducing one here would be a second, inconsistent convention rather
than a fix. The ~8-hour UTC/Philippines-local boundary discrepancy this
implies is a known, pre-existing, project-wide characteristic - not
something this helper is responsible for solving.

For a plain `Date` column (e.g. `Visit.visit_date`, `Invoice.invoice_date`,
`Appointment.appointment_date`, `Queue.queue_date`), a simple `column >=
date_from` / `column <= date_to` is correct as-is and does NOT need this
helper - it exists only for `DateTime` columns (e.g. `LaboratoryOrder.
created_at`, `VaccinationAdministration.created_at`) where an inclusive
"through end of `date_to`" requires an exclusive upper bound at the start
of the following day, not a `<=` comparison against a bare date."""

from datetime import UTC, date, datetime, timedelta
from typing import Any


def datetime_range_filters(column: Any, date_from: date | None, date_to: date | None) -> list[Any]:
    """Returns 0-2 SQLAlchemy filter expressions for `column` (a DateTime),
    given an inclusive calendar-date range. Either bound may be omitted."""
    filters: list[Any] = []
    if date_from is not None:
        filters.append(column >= datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC))
    if date_to is not None:
        upper_exclusive = datetime(date_to.year, date_to.month, date_to.day, tzinfo=UTC) + timedelta(days=1)
        filters.append(column < upper_exclusive)
    return filters
