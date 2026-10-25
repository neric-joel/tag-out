"""ICS ingest: Canvas feeds, personal calendars, job shift exports and ASU's public academic calendar.

Each event becomes either a Shift (job exports) or a private BusyBlock. Recurring events (class meetings) are
expanded with recurring-ical-events. Feed URLs are secrets: fetch_ics never logs them.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

import httpx
import icalendar
import recurring_ical_events

from core.models import BusyBlock, BusyKind, Shift
from core.timeutil import PHX

CANVAS_COURSE = re.compile(r"\s*\[[^\]]+\]\s*$")
EXAM_WORDS = re.compile(r"\b(exam|midterm|final|quiz|test)\b", re.I)
APPT_WORDS = re.compile(r"\b(dentist|doctor|dr\.|clinic|therapy|appointment|appt|checkup|vaccine)\b", re.I)
INTERVIEW_WORDS = re.compile(r"\b(interview|career fair|recruiter|onsite|phone screen)\b", re.I)
TRAVEL_WORDS = re.compile(r"\b(flight|trip|vacation|wedding|travel|home for)\b", re.I)
COURSE_CODE = re.compile(r"\b[A-Z]{3}\s?\d{3}\b")


def fetch_ics(url: str, timeout: float = 15.0) -> str:
    """Download a private feed. The URL is a secret, so errors are reported without it."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except httpx.HTTPError as e:
        raise RuntimeError(f"calendar feed unreachable ({type(e).__name__})") from None


def _to_dt(v, default_time: time = time(0, 0)) -> datetime:
    if isinstance(v, datetime):
        return v.astimezone(PHX) if v.tzinfo else v.replace(tzinfo=PHX)
    return datetime.combine(v, default_time, tzinfo=PHX)


def _events(text: str, start: date, end: date):
    cal = icalendar.Calendar.from_ical(text)
    return recurring_ical_events.of(cal).between(start, end)


def classify(summary: str, categories: list[str] | None = None) -> BusyKind:
    """Private label for an event. Explicit CATEGORIES win; otherwise cheap keyword rules."""
    cats = {c.lower() for c in categories or []}
    for kind in ("class", "exam", "due", "appointment", "interview", "vacation", "protected"):
        if kind in cats:
            return kind  # type: ignore[return-value]
    if EXAM_WORDS.search(summary):
        return "exam"
    if APPT_WORDS.search(summary):
        return "appointment"
    if INTERVIEW_WORDS.search(summary):
        return "interview"
    if TRAVEL_WORDS.search(summary):
        return "vacation"
    if re.search(r"\bdue\b", summary, re.I):
        return "due"
    if COURSE_CODE.search(summary):
        return "class"
    return "other"


def _categories(ev) -> list[str]:
    raw = ev.get("CATEGORIES")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for it in items:
        out.extend(str(c) for c in getattr(it, "cats", [it]))
    return out


def _bid(source: str, summary: str, start: datetime) -> str:
    return hashlib.sha1(f"{source}|{summary}|{start.isoformat()}".encode()).hexdigest()[:12]


def busy_from_ics(text: str, source: str, start: date, end: date) -> list[BusyBlock]:
    """Personal or Canvas calendar -> private busy blocks."""
    out: list[BusyBlock] = []
    for ev in _events(text, start, end):
        summary = str(ev.get("SUMMARY", "busy")).strip()
        if source == "canvas":
            summary = CANVAS_COURSE.sub("", summary)
        s = _to_dt(ev.get("DTSTART").dt)
        e_raw = ev.get("DTEND")
        e = _to_dt(e_raw.dt) if e_raw else s
        if not isinstance(ev.get("DTSTART").dt, datetime):  # all-day
            e = _to_dt(e_raw.dt) if e_raw else s + timedelta(days=1)
        kind = classify(summary, _categories(ev))
        if source == "canvas" and kind in ("other", "class"):
            kind = "due"
        if kind == "due" and e <= s:
            s = e - timedelta(minutes=1)
        out.append(BusyBlock(id=_bid(source, summary, s), start=s, end=max(e, s), kind=kind, label=summary,
                             source=source))  # type: ignore[arg-type]
    return sorted(out, key=lambda b: b.start)


def shifts_from_ics(text: str, employer: str, start: date, end: date, wage: float = 16.0) -> list[Shift]:
    """A job's shift export -> Shifts. The event UID is the roster's shift id."""
    out = []
    for ev in _events(text, start, end):
        s, e = _to_dt(ev.get("DTSTART").dt), _to_dt(ev.get("DTEND").dt)
        uid = str(ev.get("UID")).split("@")[0]
        out.append(Shift(id=uid, employer=employer, start=s, end=e, wage=wage))
    return sorted(out, key=lambda x: x.start)


def asu_breaks(text: str, start: date, end: date) -> list[tuple[date, date, str]]:
    """University-closed days and breaks from ASU's public academic calendar."""
    out = []
    for ev in _events(text, start, end):
        summary = str(ev.get("SUMMARY", ""))
        if re.search(r"break|holiday|university closed|observed", summary, re.I):
            s = ev.get("DTSTART").dt
            e = ev.get("DTEND").dt if ev.get("DTEND") else s
            s = s.date() if isinstance(s, datetime) else s
            e = e.date() if isinstance(e, datetime) else e
            out.append((s, e, re.sub(r"\s+", " ", summary).strip()))
    return sorted(out)


def exam_eves(blocks: list[BusyBlock]) -> list[BusyBlock]:
    """Protected study evening before each exam (5-11 PM the day before)."""
    out = []
    for b in blocks:
        if b.kind != "exam":
            continue
        eve = b.start.date() - timedelta(days=1)
        s, e = datetime.combine(eve, time(17), tzinfo=PHX), datetime.combine(eve, time(23), tzinfo=PHX)
        out.append(BusyBlock(id=_bid("protected", b.label, s), start=s, end=e, kind="protected",
                             label=f"{b.label} prep", source=b.source))
    return out


def read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
