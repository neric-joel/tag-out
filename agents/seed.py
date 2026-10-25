"""Load a demo student into their mascot's own database through the real ingest path."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from agents.store import Store
from core.models import Limits, Preferences, SoftAvoid, Student
from ingest import text as text_intake
from ingest import workday
from ingest.ics import busy_from_ics, exam_eves, read, shifts_from_ics
from seeds.org import DEPARTMENTS, JOB_PROFILES, ORG_STUDENTS
from seeds.scenario import DEMO_MONDAY, EMPLOYER, STUDENTS, WAGE

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"


def scenario_student(sid: str) -> dict:
    return next(s for s in STUDENTS + ORG_STUDENTS if s["id"] == sid)


def seed(store: Store, sid: str) -> Student:
    spec = scenario_student(sid)
    store.reset()
    prefs = dict(spec.get("prefs", {}))
    prefs["soft_avoid"] = [SoftAvoid(**a) for a in prefs.get("soft_avoid", [])]
    limits = Limits(**spec.get("limits", {}))
    time_csv = ICS.parent / "workday" / f"{sid}_time.csv"
    if time_csv.exists():  # hours history comes from Workday time entries, summed across positions
        limits = limits.model_copy(update={"hours_history": workday.history(
            workday.parse_time_csv(time_csv.read_text(encoding="utf-8")), DEMO_MONDAY),
            "hours_history_weeks": workday.history_weeks(DEMO_MONDAY)})
    dept = spec.get("dept", "library")
    profiles = spec.get("job_profiles") or JOB_PROFILES.get(sid, ["desk"])
    st = Student(id=sid, name=spec["name"], pet_id=spec["pet_id"], job_profiles=profiles, limits=limits,
                 prefs=Preferences(**prefs))
    start, end = DEMO_MONDAY - timedelta(days=7), DEMO_MONDAY + timedelta(days=14)
    employer = DEPARTMENTS[dept]["employer"] if dept != "library" else EMPLOYER
    store.set_shifts(shifts_from_ics(read(ICS / f"{sid}_{dept}.ics"), employer, start, end, WAGE), [])
    busy = busy_from_ics(read(ICS / f"{sid}_personal.ics"), "calendar", start, end)
    if (ICS / f"{sid}_canvas.ics").exists():
        canvas = busy_from_ics(read(ICS / f"{sid}_canvas.ics"), "canvas", start, end)
        busy += canvas
        if st.prefs.protect_exam_eves:
            busy += exam_eves(canvas)
    for t in spec.get("texts", []):
        parsed, _engine = text_intake.parse(t, DEMO_MONDAY)
        busy += text_intake.to_blocks(parsed)
        st = merge_prefs(st, parsed.get("preferences") or {})
    store.add_busy(busy)
    store.save_student(st)
    store.put("version", 1)
    store.note("Set up from your calendars and texts. Everything here stays with me.")
    return st


def merge_prefs(st: Student, p: dict) -> Student:
    prefs = st.prefs.model_copy()
    if p.get("wants_more_hours") is not None:
        prefs.wants_more_hours = bool(p["wants_more_hours"])
    for d in p.get("never_weekdays") or []:
        if d not in prefs.never_weekdays:
            prefs.never_weekdays.append(int(d))
    return st.model_copy(update={"prefs": prefs})
