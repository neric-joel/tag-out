"""Generate the synthetic ICS fixtures from seeds/scenario.py and trim the ASU calendar snapshot.

    python -m scripts.make_fixtures
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import icalendar

from core.timeutil import PHX
from seeds.org import DEPARTMENTS, ORG_STUDENTS
from seeds.scenario import DEMO_MONDAY, EMPLOYER, POSITIONS, STUDENTS

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"
WORKDAY = ICS.parent / "workday"
TERM_START, TERM_END = date(2026, 8, 20), date(2026, 12, 12)


def _cal(name: str) -> icalendar.Calendar:
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Tag Out synthetic fixtures//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", name)
    return cal


def _dt(day: int, hm: tuple[int, int]) -> datetime:
    return datetime.combine(DEMO_MONDAY + timedelta(days=day), time(*hm), tzinfo=PHX)


def _event(cal, uid: str, summary: str, start: datetime, end: datetime, categories: list[str] | None = None,
           rrule: dict | None = None) -> None:
    ev = icalendar.Event()
    ev.add("uid", uid)
    ev.add("summary", summary)
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("dtstamp", datetime(2026, 10, 24, 12, tzinfo=PHX))
    if categories:
        ev.add("categories", categories)
    if rrule:
        ev.add("rrule", rrule)
    cal.add_component(ev)


def shift_id(start: datetime, desk: int, prefix: str = EMPLOYER) -> str:
    """Stable roster id: the slot plus the desk position, since two people can staff the same slot."""
    return f"{prefix}-{start:%a}-{start:%m%d}-{start:%H%M}-d{desk}".lower()


def build() -> None:
    ICS.mkdir(parents=True, exist_ok=True)
    roster = _cal("Library roster (synthetic)")
    desks: dict[datetime, int] = {}
    for s in STUDENTS:
        sid = s["id"]
        job = _cal(f"{s['name']} - Library shifts (synthetic)")
        for day, a, b in s["library_shifts"]:
            st, en = _dt(day, (a, 0)), _dt(day, (b, 0))
            desks[st] = desks.get(st, 0) + 1
            uid = shift_id(st, desks[st])
            _event(job, f"{uid}@tagout", "Library desk shift", st, en)
            _event(roster, f"{uid}@tagout", f"Library desk shift - {s['name']}", st, en)
        (ICS / f"{sid}_library.ics").write_bytes(job.to_ical())
        personal_ics(s)
        if s.get("canvas"):
            canvas = _cal(f"{s['name']} - Canvas (synthetic)")
            for title, day, start, end, _kind in s["canvas"]:
                course = title.split(" ")[0] + " " + title.split(" ")[1]
                _event(canvas, f"event-assignment-{sid}-{day}@canvas", f"{title} [{course} Fall 2026]",
                       _dt(day, start), _dt(day, end))
            (ICS / f"{sid}_canvas.ics").write_bytes(canvas.to_ical())
    (ICS / "library_roster.ics").write_bytes(roster.to_ical())
    org_students()
    trim_asu()
    workday_time()


def personal_ics(s: dict) -> None:
    sid = s["id"]
    personal = _cal(f"{s['name']} - personal (synthetic)")
    first_monday = TERM_START - timedelta(days=TERM_START.weekday())
    for course, days, start, end in s.get("classes", []):
        byday = [["MO", "TU", "WE", "TH", "FR", "SA", "SU"][d] for d in days]
        first = min(days)
        st = datetime.combine(first_monday + timedelta(days=first), time(*start), tzinfo=PHX)
        en = datetime.combine(first_monday + timedelta(days=first), time(*end), tzinfo=PHX)
        _event(personal, f"{sid}-{course.replace(' ', '')}@tagout", course, st, en, ["CLASS"],
               {"freq": "weekly", "byday": byday, "until": datetime.combine(TERM_END, time(23), tzinfo=PHX)})
    for label, day, start, end, kind in s.get("calendar", []):
        cats = [kind.upper()] if kind != "other" else None
        _event(personal, f"{sid}-{label[:12].replace(' ', '')}-{day}@tagout", label, _dt(day, start),
               _dt(day, end), cats)
    for i, (label, day, start, end) in enumerate(s.get("jobs", [])):
        _event(personal, f"{sid}-job{i}@tagout", label, _dt(day, start), _dt(day, end))
    (ICS / f"{sid}_personal.ics").write_bytes(personal.to_ical())


def org_students() -> None:
    """The Dining and Rec center students (seeds/org.py): one shift export per student, like the Library's."""
    for dept, d in DEPARTMENTS.items():
        if dept == "library":
            continue
        desks: dict[datetime, int] = {}
        for s in (x for x in ORG_STUDENTS if x["dept"] == dept):
            job = _cal(f"{s['name']} - {d['name']} shifts (synthetic)")
            for day, a, b in s["shifts"]:
                st, en = _dt(day, (a, 0)), _dt(day, (b, 0))
                desks[st] = desks.get(st, 0) + 1
                _event(job, f"{shift_id(st, desks[st], dept)}@tagout", f"{d['name']} shift", st, en)
            (ICS / f"{s['id']}_{dept}.ics").write_bytes(job.to_ical())
            personal_ics(s)


def workday_time() -> None:
    """Synthetic Workday time entries for the 8 weeks before the demo week, one CSV per student."""
    WORKDAY.mkdir(parents=True, exist_ok=True)
    for s in STUDENTS:
        lim = s.get("limits", {})
        asu_other = {k: v for k, v in lim.get("other_employer_hours", {}).items()
                     if k not in lim.get("non_asu_employers", [])}
        rows = ["Date,Position,Time Type,Hours,Status"]
        for k, total in enumerate(lim.get("hours_history", [])):
            monday = DEMO_MONDAY - timedelta(days=7 * (len(lim["hours_history"]) - k))
            parts = {POSITIONS["library"]: total - sum(asu_other.values())}
            parts |= {POSITIONS[name]: h for name, h in asu_other.items()}
            for d, (position, hours) in enumerate(parts.items()):
                day, left = d, hours
                while left > 0:  # one entry per working day, 4 h blocks, as students enter elapsed time
                    block = min(4.0, left)
                    rows.append(f"{monday + timedelta(days=day % 6):%Y-%m-%d},{position},Regular Hours Worked - "
                                f"Elapsed,{block:g},Approved")
                    left -= block
                    day += 2
        (WORKDAY / f"{s['id']}_time.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def trim_asu() -> None:
    """Keep 2026-27 events from the ASU public academic calendar snapshot (fetched Oct 24 2026)."""
    path = ICS / "asu_academic.ics"
    if not path.exists():
        return
    cal = icalendar.Calendar.from_ical(path.read_bytes())
    out = _cal("ASU academic calendar (public snapshot, fetched 2026-10-24, 2026-27 only)")
    for ev in cal.walk("VEVENT"):
        d = ev.get("DTSTART").dt
        d = d.date() if isinstance(d, datetime) else d
        if date(2026, 7, 1) <= d <= date(2027, 8, 31):
            out.add_component(ev)
    path.write_bytes(out.to_ical())


if __name__ == "__main__":
    build()
    print("fixtures written to", ICS)
