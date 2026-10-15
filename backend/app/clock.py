"""Demo clock and period helpers. All period logic goes through get_now(), never datetime.now()."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.models import Setting

LONDON = ZoneInfo("Europe/London")

DEMO_NOW_KEY = "demo_now"
START_PERIOD_KEY = "tab_start_period"


def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.get(Setting, key)
    return row.value if row is not None else default


def set_setting(session: Session, key: str, value: str | None) -> None:
    row = session.get(Setting, key)
    if value is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
        session.add(row)
    session.commit()


def parse_aware(value: str) -> datetime:
    """Parse an ISO datetime. Naive values are read as Europe/London local time."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LONDON)
    return dt.astimezone(timezone.utc)


def get_now(session: Session) -> datetime:
    """The app's 'now': the demo clock if set, else the real UTC time."""
    override = get_setting(session, DEMO_NOW_KEY)
    if override:
        return parse_aware(override)
    return datetime.now(timezone.utc)


def set_demo_now(session: Session, value: datetime | None) -> None:
    set_setting(session, DEMO_NOW_KEY, value.astimezone(timezone.utc).isoformat() if value else None)


def period_of(dt: datetime) -> str:
    return dt.astimezone(LONDON).strftime("%Y-%m")


def parse_period(period: str) -> tuple[int, int]:
    year, month = period.split("-")
    y, m = int(year), int(month)
    if not 1 <= m <= 12:
        raise ValueError(f"bad period {period!r}")
    return y, m


def next_period(period: str) -> str:
    y, m = parse_period(period)
    return f"{y + (m == 12)}-{(m % 12) + 1:02d}"


def previous_period(period: str) -> str:
    y, m = parse_period(period)
    return f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"


def period_bounds(period: str) -> tuple[datetime, datetime]:
    """[start, end) of a calendar month in London time, returned as UTC."""
    y, m = parse_period(period)
    start = datetime(y, m, 1, tzinfo=LONDON)
    ny, nm = parse_period(next_period(period))
    end = datetime(ny, nm, 1, tzinfo=LONDON)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def invoice_due_at(period: str, invoice_day_of_month: int) -> datetime:
    """When the invoice for `period` may be raised: that day of the following month, 00:00 London."""
    ny, nm = parse_period(next_period(period))
    last_day = calendar.monthrange(ny, nm)[1]
    day = max(1, min(invoice_day_of_month, last_day))
    return datetime(ny, nm, day, tzinfo=LONDON).astimezone(timezone.utc)


def is_period_closed_for_billing(period: str, now: datetime, invoice_day_of_month: int) -> bool:
    return now >= invoice_due_at(period, invoice_day_of_month)


def period_label(period: str) -> str:
    y, m = parse_period(period)
    return f"{calendar.month_name[m]} {y}"


def london(dt: datetime) -> datetime:
    return dt.astimezone(LONDON)


def fmt_london(dt: datetime) -> str:
    return dt.astimezone(LONDON).strftime("%Y-%m-%d %H:%M")


def fmt_day(dt: datetime) -> str:
    d = dt.astimezone(LONDON)
    return f"{d.day} {d.strftime('%b')}"


def days_between(a: datetime, b: datetime) -> int:
    """Whole calendar days from a to b, in London dates."""
    return (b.astimezone(LONDON).date() - a.astimezone(LONDON).date()).days


__all__ = [
    "LONDON", "days_between", "fmt_day", "fmt_london", "get_now", "get_setting", "invoice_due_at",
    "is_period_closed_for_billing", "london", "next_period", "parse_aware", "period_bounds",
    "period_label", "period_of", "previous_period", "set_demo_now", "set_setting", "timedelta",
]
