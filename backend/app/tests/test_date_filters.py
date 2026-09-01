"""Unit tests for the shared `datetime_range_filters` helper (recent-
records date-range filtering convention). Pure function, no DB - applies
the returned filter expressions against a real query in the integration
tests of each affected repository (Laboratory, Vaccination) instead."""

from datetime import date

from sqlalchemy import Column, DateTime, MetaData, Table, select

from app.db.date_filters import datetime_range_filters

_metadata = MetaData()
_table = Table("dummy", _metadata, Column("created_at", DateTime(timezone=True)))
_column = _table.c.created_at


def _compiled(filters: list) -> str:
    stmt = select(_table).where(*filters)
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_no_bounds_returns_no_filters():
    assert datetime_range_filters(_column, None, None) == []


def test_date_from_only_produces_a_single_inclusive_lower_bound():
    filters = datetime_range_filters(_column, date(2026, 3, 5), None)
    assert len(filters) == 1
    sql = _compiled(filters)
    assert "2026-03-05 00:00:00" in sql
    assert ">=" in sql


def test_date_to_only_produces_an_exclusive_upper_bound_at_the_next_day():
    filters = datetime_range_filters(_column, None, date(2026, 3, 5))
    assert len(filters) == 1
    sql = _compiled(filters)
    # Inclusive "through end of March 5" = exclusive "< March 6 00:00:00",
    # never a `<=` against the bare date (which would silently exclude
    # every timestamp later than midnight on the 5th itself).
    assert "2026-03-06 00:00:00" in sql
    assert "<" in sql
    assert "<=" not in sql


def test_both_bounds_produce_two_filters_with_correct_boundaries():
    filters = datetime_range_filters(_column, date(2026, 1, 1), date(2026, 1, 31))
    assert len(filters) == 2
    sql = _compiled(filters)
    assert "2026-01-01 00:00:00" in sql
    assert "2026-02-01 00:00:00" in sql


def test_single_day_range_captures_the_whole_day_not_just_midnight():
    """The 'Today' preset resolves to date_from == date_to == today - this
    must still capture every timestamp on that calendar day (e.g.
    23:59:59), not just midnight itself."""
    today = date(2026, 6, 15)
    filters = datetime_range_filters(_column, today, today)
    assert len(filters) == 2
    sql = _compiled(filters)
    assert "2026-06-15 00:00:00" in sql
    assert "2026-06-16 00:00:00" in sql
