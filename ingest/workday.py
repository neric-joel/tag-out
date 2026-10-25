"""Workday time import: a student's time entries -> ASU hours per Mon-Sun week.

ASU student workers enter time in Workday ("Enter My Time": Mon-Sun weeks inside a biweekly time period, one
"Regular Hours Worked" entry per day, each approved by the supervisor). This reads the same rows as a CSV, the
shape of a "Review Time by Week" export: Date, Position, Time Type, Hours, Status. Hours from every position are
summed, because the 25 h average counts all ASU jobs together.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from core.timeutil import week_start

COUNTED = {"Approved", "Submitted"}  # draft or sent-back entries are not counted


@dataclass(frozen=True)
class TimeEntry:
    day: date
    position: str
    time_type: str
    hours: float
    status: str


def parse_time_csv(text: str) -> list[TimeEntry]:
    rows = csv.DictReader(io.StringIO(text))
    out = []
    for r in rows:
        try:
            out.append(TimeEntry(date.fromisoformat(r["Date"].strip()), r["Position"].strip(),
                                 r.get("Time Type", "").strip(), float(r["Hours"]), r.get("Status", "").strip()))
        except (KeyError, ValueError):
            continue  # a malformed row is skipped, never guessed
    return out


def weekly_totals(entries: list[TimeEntry]) -> dict[date, float]:
    totals: dict[date, float] = defaultdict(float)
    for e in entries:
        if e.status in COUNTED:
            totals[week_start(e.day)] += e.hours
    return dict(totals)


def history(entries: list[TimeEntry], before: date, weeks: int = 8) -> list[float]:
    """The last `weeks` Mon-Sun totals before the week starting `before`; a week with no entries counts as 0."""
    totals = weekly_totals(entries)
    mondays = [week_start(before) - timedelta(days=7 * k) for k in range(weeks, 0, -1)]
    return [round(totals.get(m, 0.0), 2) for m in mondays]


def positions(entries: list[TimeEntry]) -> list[str]:
    return sorted({e.position for e in entries})
