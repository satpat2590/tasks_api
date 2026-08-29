"""Regression tests for calculate_next_due_date anchoring.

Bug (2026-08-29): next_due was anchored on the STORED due_date, so a daily
task whose due_date had drifted to 2027-01-16 kept returning 2027-01-17,
2027-01-18, ... forever — WHOOP auto-complete then refused/falsely reported
the next due date. Fix: anchor on completed_at, keep stored time-of-day.
"""
from datetime import datetime, timedelta, timezone

from main import calculate_next_due_date

NOW = datetime(2026, 8, 29, 14, 31, 6, tzinfo=timezone.utc)


def test_daily_drifted_due_dates_to_tomorrow():
    stored = datetime(2027, 1, 16, 4, 59, tzinfo=timezone.utc)  # drifted far future
    nd = calculate_next_due_date(stored, "daily", completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(days=1)
    assert nd.hour == 4 and nd.minute == 59  # time-of-day preserved


def test_daily_stale_past_due():
    stored = datetime(2026, 8, 20, 4, 59, tzinfo=timezone.utc)  # overdue by 9 days
    nd = calculate_next_due_date(stored, "daily", completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(days=1)


def test_daily_same_day_boundary():
    stored = datetime(2026, 8, 29, 4, 59, tzinfo=timezone.utc)
    nd = calculate_next_due_date(stored, "daily", completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(days=1)


def test_weekly():
    stored = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)
    nd = calculate_next_due_date(stored, "weekly", completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(weeks=1)


def test_every_n_days():
    stored = datetime(2027, 1, 16, 4, 59, tzinfo=timezone.utc)
    nd = calculate_next_due_date(stored, "every 3 days", completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(days=3)


def test_no_completed_at_falls_back_to_current_due():
    stored = datetime(2026, 8, 29, 4, 59, tzinfo=timezone.utc)
    nd = calculate_next_due_date(stored, "daily")
    assert nd.date() == stored.date() + timedelta(days=1)


def test_unknown_pattern_defaults_weekly():
    stored = datetime(2026, 8, 29, 4, 59, tzinfo=timezone.utc)
    nd = calculate_next_due_date(stored, None, completed_at=NOW)
    assert nd.date() == NOW.date() + timedelta(weeks=1)
