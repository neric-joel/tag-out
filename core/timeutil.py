"""Time helpers. Everything user-facing is America/Phoenix (UTC-7, no DST)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PHX = ZoneInfo("America/Phoenix")
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=PHX)


def week_start(d: date) -> date:
    """Monday of the Mon-Sun week containing d (the F-1 counting week)."""
    return d - timedelta(days=d.weekday())


def week_days(monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(7)]


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def fmt_hour(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}" if dt.minute == 0 else f"{h}:{dt.minute:02d}"


def fmt_span(start: datetime, end: datetime) -> str:
    """'Tue 6-10 PM' style label, the way students write shifts."""
    start, end = start.astimezone(PHX), end.astimezone(PHX)
    day = DAY_NAMES[start.weekday()]
    suffix = "PM" if end.hour >= 12 else "AM"
    if (start.hour < 12) != (end.hour < 12) and end.hour != 12:
        return f"{day} {fmt_hour(start)} {'PM' if start.hour >= 12 else 'AM'}-{fmt_hour(end)} {suffix}"
    return f"{day} {fmt_hour(start)}-{fmt_hour(end)} {suffix}"
