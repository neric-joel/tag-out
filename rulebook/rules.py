"""The Rulebook: pure functions over one student's private numbers.

Each mascot calls this privately. Nothing here talks to the network or an LLM. Limits come from config/rules.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from core.models import BusyBlock, Shift, Student
from core.timeutil import week_start
from rulebook.quotes import quote_for

CONFIG = Path(__file__).resolve().parent.parent / "config" / "rules.yaml"
Status = Literal["eligible", "blocked", "unverified"]


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["rules"]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    status: Status
    detail: str  # private, for the owner's diary only


@dataclass(frozen=True)
class Verdict:
    status: Status
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Safe to trade into. Unverified counts as ok for swaps that keep hours flat, never for added hours."""
        return self.status != "blocked"

    @property
    def deciding(self) -> Finding | None:
        for wanted in ("blocked", "unverified"):
            for f in self.findings:
                if f.status == wanted:
                    return f
        return None

    def cite(self) -> tuple[str | None, str | None]:
        f = self.deciding
        return quote_for(f.rule_id) if f else (None, None)


@dataclass(frozen=True)
class Room:
    rule_id: str
    used: float
    cap: float
    room: float
    unit: str = "h"


def in_break_week(monday: date) -> bool:
    for p in config()["f1_break_40"]["break_periods"]:
        start, end = p["start"], p["end"]
        if start <= monday <= end:
            return True
    return False


def week_hours(student: Student, shifts: list[Shift], monday: date) -> float:
    """Hours in the Mon-Sun week across every employer, including ones this employer can't see."""
    own = sum(s.hours for s in shifts if week_start(s.start.date()) == monday)
    return own + sum(student.limits.other_employer_hours.values())


def asu_week_hours(student: Student, shifts: list[Shift], monday: date) -> float:
    """Hours that count toward ASU's 25 h average: ASU jobs and stipends only (Aramark, Follett excluded)."""
    own = sum(s.hours for s in shifts if week_start(s.start.date()) == monday)
    lim = student.limits
    return own + sum(h for k, h in lim.other_employer_hours.items() if k not in lim.non_asu_employers)


def measurement_window(student: Student, monday: date) -> tuple[date, date, str]:
    """The 25 h average's measurement period: 12 months starting the first of the month after the hire date
    (ASU's ACA FAQ), then the standard Oct 1 - Sep 30 period."""
    hire = student.limits.hire_date
    if hire:
        start = date(hire.year + (hire.month == 12), hire.month % 12 + 1, 1)
        end = date(start.year + 1, start.month, 1)
        if monday < end:
            return start, end, "initial"
    start_year = monday.year if monday.month >= 10 else monday.year - 1
    return date(start_year, 10, 1), date(start_year + 1, 9, 30), "standard"


def period_history(student: Student, monday: date) -> tuple[list[float], date]:
    """ASU weekly hours inside the current measurement period, before this week. Without dated history (no
    Workday import), every recorded week is used, which is the stricter reading."""
    lim = student.limits
    start, _end, _kind = measurement_window(student, monday)
    hist = lim.hours_history or []
    if lim.hours_history_weeks and len(lim.hours_history_weeks) == len(hist):
        return [h for w, h in zip(lim.hours_history_weeks, hist, strict=True) if start <= w < monday], start
    return list(hist), start


def f1_buffer() -> float:
    """Tag Out asks the student before a trade takes them within this many hours of the F-1 limit."""
    return float(config()["f1_weekly_20"].get("buffer_hours", 0))


def near_f1_limit(student: Student, shifts_after: list[Shift], monday: date) -> bool:
    if not student.limits.f1_or_j1:
        return False
    total = week_hours(student, shifts_after, monday)
    cap = f1_cap_for(student, monday)
    return cap - f1_buffer() < total <= cap


def week_pay(shifts: list[Shift], monday: date) -> float:
    return sum(s.pay for s in shifts if week_start(s.start.date()) == monday)


def f1_cap(monday: date) -> float:
    """The weekly limit for a continuing F-1/J-1 student in this week (see f1_cap_for for one student)."""
    if in_break_week(monday):
        return float(config()["f1_break_40"]["weekly_hours"])
    return float(config()["f1_weekly_20"]["weekly_hours"])


def f1_cap_for(student: Student, monday: date) -> float:
    """ISSC: 40 h in a listed break only if enrolled (or planning to enroll) for the next term, and no on-campus
    work after the program completion date. Unknown enrollment stays at the safer 20 h."""
    lim = student.limits
    if lim.program_end and monday > lim.program_end:
        return 0.0
    if in_break_week(monday) and not lim.f1_continuing:
        return float(config()["f1_weekly_20"]["weekly_hours"])
    return f1_cap(monday)


def rooms(student: Student, shifts: list[Shift], monday: date) -> list[Room]:
    """Room left before each limit that applies to this student. The smallest one binds."""
    lim = student.limits
    total = week_hours(student, shifts, monday)
    out = [Room("weekly_40", total, float(config()["weekly_40"]["weekly_hours"]),
                config()["weekly_40"]["weekly_hours"] - total)]
    if lim.f1_or_j1:
        cap = f1_cap_for(student, monday)
        out.append(Room("f1_break_40" if in_break_week(monday) else "f1_weekly_20", total, cap, cap - total))
    if lim.hours_history:
        avg_cap = float(config()["aca_25_avg"]["average_hours"])
        hist, _start = period_history(student, monday)
        asu = asu_week_hours(student, shifts, monday)
        allowed = avg_cap * (len(hist) + 1) - sum(hist)
        out.append(Room("aca_25_avg", asu, allowed, allowed - asu))
    if lim.fws and lim.fws_award_remaining is not None:
        paid = week_pay(shifts, monday)
        out.append(Room("fws_award", paid, lim.fws_award_remaining, lim.fws_award_remaining - paid, unit="$"))
    return out


def next_break(monday: date) -> date | None:
    """The first day of the next ASU-listed break after this Monday."""
    starts = sorted(b["start"] if isinstance(b["start"], date) else date.fromisoformat(str(b["start"]))
                    for b in config()["f1_break_40"]["break_periods"])
    return next((d for d in starts if d > monday), None)


def term_weeks_left(monday: date) -> int | None:
    """Whole weeks from this Monday to the next ASU-listed break."""
    nxt = next_break(monday)
    return (nxt - monday).days // 7 if nxt else None


def fws_runway(student: Student, shifts: list[Shift], monday: date) -> tuple[float, float, int] | None:
    """When a Work-Study award runs out before the next break at this week's scheduled pay:
    (weeks it lasts, this week's pay, weeks to the break). None when it lasts, or can't be known."""
    lim = student.limits
    weeks_left = term_weeks_left(monday)
    paid = week_pay(shifts, monday)
    if not lim.fws or lim.fws_award_remaining is None or not paid or weeks_left is None:
        return None
    lasts = lim.fws_award_remaining / paid
    return (lasts, paid, weeks_left) if lasts < weeks_left else None


def binding(student: Student, shifts: list[Shift], monday: date, wage: float = 16.0) -> Room:
    """The limit that binds first, comparing dollars as hours at this wage."""
    def as_hours(r: Room) -> float:
        return r.room / wage if r.unit == "$" else r.room
    return min(rooms(student, shifts, monday), key=as_hours)


def evaluate(
    student: Student,
    shifts_after: list[Shift],
    busy: list[BusyBlock],
    monday: date,
    added_pay: float = 0.0,
) -> Verdict:
    """Check a whole week as it would look after a change."""
    lim = student.limits
    findings: list[Finding] = []
    week = [s for s in shifts_after if week_start(s.start.date()) == monday]
    total = week_hours(student, week, monday)

    classes = [b for b in busy if b.kind == "class"]
    clash = next(((s, c) for s in week for c in classes if s.hits(c.start, c.end)), None)
    findings.append(Finding(
        "class_time", "blocked" if clash else "eligible",
        f"{clash[0].label} overlaps {clash[1].label}" if clash else "no shift during your classes"))

    cap40 = config()["weekly_40"]["weekly_hours"]
    findings.append(Finding("weekly_40", "blocked" if total > cap40 else "eligible", f"{total:g} h of {cap40} h"))

    if lim.f1_or_j1:
        cap = f1_cap_for(student, monday)
        rid = "f1_break_40" if in_break_week(monday) and cap > 20 else "f1_weekly_20"
        findings.append(Finding(rid, "blocked" if total > cap else "eligible",
                                f"{total:g} h this week across all on-campus jobs, limit {cap:g}"))

    avg_cap = config()["aca_25_avg"]["average_hours"]
    if lim.hours_history:
        hist, start = period_history(student, monday)
        projected = (sum(hist) + asu_week_hours(student, week, monday)) / (len(hist) + 1)
        findings.append(Finding("aca_25_avg", "blocked" if projected > avg_cap else "eligible",
                                f"projected average {projected:.1f} h of {avg_cap} h over the measurement period so "
                                f"far ({len(hist) + 1} weeks since {start:%b %d %Y})"))
    else:
        findings.append(Finding("aca_25_avg", "unverified",
                                "no hours history yet, so the 25 h average can't be checked"))

    if lim.fws:
        remaining = lim.fws_award_remaining
        if remaining is None:
            findings.append(Finding("fws_award", "unverified", "award balance unknown"))
        else:
            paid = week_pay(week, monday)  # everything scheduled this week counts, not only what a trade adds
            findings.append(Finding("fws_award", "blocked" if paid > remaining else "eligible",
                                    f"${paid:.0f} scheduled this week against ${remaining:.0f} left on the award"))

    statuses = {f.status for f in findings}
    status: Status = "blocked" if "blocked" in statuses else "unverified" if "unverified" in statuses else "eligible"
    return Verdict(status, findings)


def check_change(
    student: Student,
    current: list[Shift],
    add: list[Shift],
    drop: list[Shift],
    busy: list[BusyBlock],
) -> Verdict:
    """Would this exact set of moves keep the student inside every limit, for every week it touches?"""
    drop_ids = {s.id for s in drop}
    after = [s for s in current if s.id not in drop_ids] + list(add)
    added_pay = sum(s.pay for s in add) - sum(s.pay for s in drop)
    touched = list(add) + list(drop) or after
    weeks = sorted({week_start(s.start.date()) for s in touched}) or [week_start(date.today())]
    worst = Verdict("eligible", [])
    for monday in weeks:
        v = evaluate(student, after, busy, monday, added_pay=max(0.0, added_pay))
        rank = {"eligible": 0, "unverified": 1, "blocked": 2}
        if rank[v.status] > rank[worst.status] or not worst.findings:
            worst = v
    # Adding net hours with an unverifiable average is not safe: treat as blocked for covers.
    net_hours = sum(s.hours for s in add) - sum(s.hours for s in drop)
    if worst.status == "unverified" and net_hours > 0:
        return Verdict("blocked", worst.findings)
    return worst
