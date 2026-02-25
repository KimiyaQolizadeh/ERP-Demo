# backend/app/utils/dates.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def utcnow() -> datetime:
    """UTC now as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def month_start(d: date) -> date:
    """First day of month for a given date."""
    return date(d.year, d.month, 1)


def next_month_start(d: date) -> date:
    """First day of the next month."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def week_start(d: date, week_starts_on: int = 0) -> date:
    """
    Return the week start date.
    week_starts_on: 0=Monday, 6=Sunday
    """
    delta = (d.weekday() - week_starts_on) % 7
    return d - timedelta(days=delta)


def week_end(d: date, week_starts_on: int = 0) -> date:
    """Return the week end date for the week containing date d."""
    return week_start(d, week_starts_on) + timedelta(days=6)


def clamp_date(d: date, start: date, end: date) -> date:
    """Clamp d to [start, end]."""
    if d < start:
        return start
    if d > end:
        return end
    return d


def parse_yyyy_mm(s: str) -> date:
    """Parse YYYY-MM into a date (first day of that month)."""
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError("Expected YYYY-MM")
    y = int(parts[0])
    m = int(parts[1])
    return date(y, m, 1)