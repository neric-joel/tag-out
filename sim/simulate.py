"""Ring simulator: how many shift conflicts plain covers fix, and how many more Tag Out's rings and chains fix.

    python -m sim.simulate --weeks 1000 --seed 7

writes docs/SIMULATION.md and docs/img/simulation.png. Every simulated week is a fresh synthetic 40-person Library
roster. Every move is checked with the real Rulebook (rulebook.rules.check_change), rings come from the real TTC and
chains from broker/ttc.py, and every final schedule is re-checked with rulebook.rules.evaluate.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from broker.ttc import chains, ttc
from core.models import BusyBlock, Limits, Preferences, Shift, SoftAvoid, Student
from core.timeutil import at
from rulebook.rules import Verdict, check_change, evaluate, week_hours
from sim.oracle import max_conflicts_solved

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "SIMULATION.md"
IMG = ROOT / "docs" / "img" / "simulation.png"
FOOTER = "Synthetic data. Not legal or immigration advice. Your DSO and ASU Student Employment decide."


@dataclass(frozen=True)
class Params:
    """Every model parameter, each with its source or marked as an assumption."""

    students: int = 40  # task brief and docs/DESIGN.md s7: one 40-person Library roster
    wage: float = 16.0  # docs/DESIGN.md s7 "same wage"; seeds/scenario.py WAGE
    shift_hours: int = 4  # docs/DESIGN.md s7 "equal 4-hour shifts"
    slot_starts: tuple[int, ...] = (10, 14, 18)  # task brief: 10-14, 14-18, 18-22 every day
    shifts_per_student: tuple[int, int] = (2, 4)  # task brief: 2-4 shifts a week (8-16 h)
    f1_share: float = 0.10  # docs/DESIGN.md s7: 10% F-1
    f1_other_hours: tuple[int, int] = (0, 9)  # task brief: 0-9 h/week at another on-campus employer
    fws_share: float = 0.20  # docs/DESIGN.md s7: 20% Federal Work-Study (domestic only; DESIGN s3)
    fws_award_remaining: tuple[float, float] = (0.0, 400.0)  # task brief: $0-$400 left on the award
    history_weeks: int = 8  # task brief: 8 weeks of hours history for everyone
    history_noise: float = 2.0  # assumption: past weekly totals vary +-2 h around the usual load
    near_cap_share: float = 0.10  # assumption ("a few near the 25 h average"): a second ASU job puts them at 22-25 h
    courses: int = 12  # assumption: the roster shares 12 courses, so exams pile onto the same evenings
    courses_per_student: int = 4  # assumption: a 12-credit load
    clustered_share: float = 0.5  # assumption: half of all conflicts are shared-course exam evenings (18-22)
    extra_events_per_student: int = 1  # assumption: one more 2-3 h event a week that only blocks cover time
    fri_evening_avoid_share: float = 0.40  # task brief: 40% never take Friday-evening shifts
    wants_hours_share: float = 0.30  # task brief: 30% want more hours; only they act as cover helpers
    helper_extra_shifts: int | None = 2  # assumption: someone who wants hours takes at most 2 extra shifts a week
    release_passers: bool = True  # broker/ttc.py: a passer keeps their shift and leaves; the rest re-point (standard TTC)
    conflict_rates: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 0.25)  # task brief sweep
    central_rate: float = 0.15  # task brief: central conflict rate
    adoption: tuple[float, ...] = (0.25, 0.50, 1.00)  # task brief: share of the roster on Tag Out
    go_points: float = 10.0  # docs/DESIGN.md s7 go/no-go: rings and chains must add 10 points
    term_monday: date = date(2026, 10, 26)  # an in-session week (the demo week in seeds/scenario.py)
    break_mondays: tuple[date, ...] = (date(2026, 12, 14), date(2026, 12, 21), date(2026, 12, 28),
                                       date(2027, 1, 4))  # config/rules.yaml: winter break Dec 14 - Jan 10
    going_home_share: float = 0.5  # task brief: half of domestic students go home and want every shift gone
    break_helper_extra_shifts: int = 4  # assumption: someone staying over break takes at most 4 extra shifts


# 18 distinct meeting patterns; each course gets one, so two courses never meet at the same time.
COURSE_STARTS = [(8, 0), (9, 0), (10, 30), (12, 0), (13, 30), (15, 0), (16, 30), (18, 0), (19, 30)]
COURSE_PATTERNS = [((0, 2, 4), 50), ((1, 3), 75)]  # MWF 50 min, TTh 75 min
EXAM_EVES = (6, 0, 1, 2, 3)  # Sun-Thu evenings, before Mon-Fri exams
EVENT_KINDS = ("appointment", "interview", "other")


@dataclass
class Person:
    student: Student
    shifts: tuple[str, ...]  # shift ids at the start of the week
    busy: list[BusyBlock]
    cannot: set[tuple[int, int]]  # (weekday, start hour) slots they can't work: busy, class, or never-Friday
    taste: dict[tuple[int, int], float]  # private slot preference, used to rank picks
    enrolled: tuple[int, ...]

    @property
    def wants_hours(self) -> bool:
        return self.student.prefs.wants_more_hours


@dataclass
class Week:
    monday: date
    people: dict[str, Person]
    shift: dict[str, Shift]
    owner: dict[str, str]  # shift id -> who holds it at the start of the week
    conflicts: list[str]  # conflicted shift ids, in the order the group chat sees them
    replies: dict[str, list[str]]  # per conflict: the order in which coworkers who want hours answer
    adopter_order: list[str]  # the first 25% / 50% / 100% of this list are on Tag Out (nested)
    verdicts: dict[tuple, Verdict] = field(default_factory=dict)  # memo for check_change within this week

    def adopters(self, share: float) -> set[str]:
        return set(self.adopter_order[:round(share * len(self.adopter_order))])

    def slot(self, sid: str) -> tuple[int, int]:
        s = self.shift[sid]
        return s.start.weekday(), s.start.hour


class Plan:
    """One way the week could play out: who holds which shift, and which conflicts got fixed how."""

    def __init__(self, week: Week):
        self.week = week
        self.held = {pid: list(p.shifts) for pid, p in week.people.items()}
        self.holder = dict(week.owner)
        self.fixed: dict[str, str] = {}  # conflicted shift id -> "ring" | "chain" | "cover"
        self.rings: list[int] = []  # size of each ring that committed

    def copy(self) -> Plan:
        other = Plan(self.week)
        other.held = {pid: list(v) for pid, v in self.held.items()}
        other.holder = dict(self.holder)
        other.fixed = dict(self.fixed)
        other.rings = list(self.rings)
        return other

    def pay_change(self, pid: str) -> float:
        w = self.week
        return sum(w.shift[s].pay for s in self.held[pid]) - sum(w.shift[s].pay for s in w.people[pid].shifts)

    def pay_lost(self) -> float:
        """Pay students lost this week: a shift moved away with nothing taken back."""
        return sum(max(0.0, -self.pay_change(pid)) for pid in self.held)

    def count(self, how: str | None = None) -> int:
        return sum(1 for h in self.fixed.values() if how is None or h == how)


# ---- rule checks -------------------------------------------------------------------------------------------------

def verdict(plan: Plan, pid: str, add: list[str], drop: list[str]) -> Verdict:
    """rulebook.rules.check_change for this person as they stand in this plan."""
    p = plan.week.people[pid]
    student = p.student
    award = student.limits.fws_award_remaining
    if student.limits.fws and award is not None:
        award = max(0.0, award - max(0.0, plan.pay_change(pid)))  # what is left after shifts already taken
    key = (pid, award, frozenset(plan.held[pid]), tuple(add), tuple(drop))
    memo = plan.week.verdicts
    if key not in memo:
        if award != student.limits.fws_award_remaining:
            student = student.model_copy(update={"limits": student.limits.model_copy(
                update={"fws_award_remaining": award})})
        sh = plan.week.shift
        memo[key] = check_change(student, [sh[s] for s in plan.held[pid]], [sh[s] for s in add],
                                      [sh[s] for s in drop], p.busy)
    return memo[key]


def free(plan: Plan, pid: str, add: list[str], drop: list[str], cap: int | None) -> bool:
    """Time and willingness only: not busy, not double-booked, not a slot they never take, under their extra cap."""
    w = plan.week
    p = w.people[pid]
    taken = {w.slot(s) for s in plan.held[pid] if s not in drop}
    for sid in add:
        slot = w.slot(sid)
        if slot in p.cannot or slot in taken:
            return False
        taken.add(slot)
    net = len(add) - len(drop)
    return net <= 0 or cap is None or len(plan.held[pid]) + net - len(p.shifts) <= cap


def allowed(plan: Plan, pid: str, add: list[str], drop: list[str], cap: int | None) -> bool:
    return free(plan, pid, add, drop, cap) and verdict(plan, pid, add, drop).ok


def commit(plan: Plan, moves: dict[str, tuple[list[str], list[str]]], cap: int | None) -> bool:
    """Every member re-checks the exact final moves (the 2PC prepare); any no aborts the whole group."""
    if not all(allowed(plan, pid, add, drop, cap) for pid, (add, drop) in moves.items()):
        return False
    for pid, (add, drop) in moves.items():
        plan.held[pid] = [s for s in plan.held[pid] if s not in drop] + add
        for s in add:
            plan.holder[s] = pid
    return True


def merge(moves: list[tuple[str, str | None, str | None]]) -> dict[str, tuple[list[str], list[str]]]:
    """[(person, add, drop)] -> {person: (adds, drops)}; one person can sit in a ring twice."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    for pid, add, drop in moves:
        a, d = out.setdefault(pid, ([], []))
        if add:
            a.append(add)
        if drop:
            d.append(drop)
    return out


def ranked(plan: Plan, pid: str, items: list[str]) -> list[str]:
    taste = plan.week.people[pid].taste
    return sorted(items, key=lambda s: (-taste[plan.week.slot(s)], s))


# ---- the three ways a conflict gets fixed --------------------------------------------------------------------------

def plain_covers(plan: Plan, cap: int | None) -> Plan:
    """The group chat, done carefully: each open conflict goes to the first coworker who wants hours, is free, and
    stays inside every limit. The owner loses that shift's pay."""
    w = plan.week
    for c in w.conflicts:
        if c in plan.fixed:
            continue
        owner = plan.holder[c]
        for h in w.replies[c]:
            if h != owner and commit(plan, merge([(h, c, None), (owner, None, c)]), cap):
                plan.fixed[c] = "cover"
                break
    return plan


def swap_prefs(plan: Plan, agents: list[str], cap: int | None) -> dict[str, list[str]]:
    """Each conflicted shift is one TTC agent. Its picks: other conflicted shifts its holder would take instead."""
    prefs = {}
    for a in agents:
        pid = plan.holder[a]
        ok = [b for b in agents if plan.holder[b] != pid and allowed(plan, pid, [b], [a], cap)]
        prefs[a] = ranked(plan, pid, ok)
    return prefs


def rings(plan: Plan, agents: list[str], cap: int | None, release_passers: bool = True) -> Plan:
    """broker.ttc.ttc over the picks. With release_passers (the broker's behaviour), a shift whose holder passes is
    withdrawn and TTC runs again on the rest (standard TTC with outside options); without it, a single pass."""
    prefs = swap_prefs(plan, agents, cap)
    remaining = list(agents)
    while remaining:
        cycles, history = ttc({a: [b for b in prefs[a] if b in remaining] for a in remaining},
                              {a: a for a in remaining}, release_passers=False)  # this loop does the release
        for cyc in cycles:  # [a, b, c]: a's holder takes b, b's holder takes c, c's holder takes a
            moves = merge([(plan.holder[x], cyc[(j + 1) % len(cyc)], x) for j, x in enumerate(cyc)])
            if commit(plan, moves, cap):
                plan.fixed.update({x: "ring" for x in cyc})
                plan.rings.append(len(cyc))
        done = {x for cyc in cycles for x in cyc}
        passers = {a for a, pick in history[-1].items() if pick is None} - done if history else set()
        if not release_passers or not passers:
            break
        remaining = [a for a in remaining if a not in done | passers]
    return plan


def cover_chains(plan: Plan, adopters: set[str], cap: int | None) -> Plan:
    """A helper covers one open shift; its owner may take another open shift hours-neutral, and so on."""
    w = plan.week
    open_ = [c for c in w.conflicts if c not in plan.fixed and w.owner[c] in adopters]
    helpers = [pid for pid in sorted(adopters) if w.people[pid].wants_hours]
    helper_prefs = {h: ranked(plan, h, [i for i in open_ if allowed(plan, h, [i], [], cap)]) for h in helpers}
    extend_prefs = {a: ranked(plan, plan.holder[a], [i for i in open_ if plan.holder[i] != plan.holder[a]
                                                      and allowed(plan, plan.holder[a], [i], [a], cap)])
                    for a in open_}
    for chain in chains(helper_prefs, extend_prefs, set(open_), {i: i for i in open_}):
        h, items = chain[0], chain[1:]
        for j in range(len(items), 0, -1):  # if the full chain fails its re-check, try a shorter one
            part = items[:j]
            moves = [(h, part[0], None)] + [(plan.holder[x], part[k + 1] if k + 1 < j else None, x)
                                             for k, x in enumerate(part)]
            if commit(plan, merge(moves), cap):
                plan.fixed.update({x: "chain" if j > 1 else "cover" for x in part})
                break
    return plan


def tag_out(week: Week, adopters: set[str], cap: int | None, plain: Plan,
            release_passers: bool = True) -> tuple[Plan, bool]:
    """Rings first (nobody loses pay), then chains, then plain covers for whatever is left.

    The broker never proposes a plan worse than plain covers: if rings-first fixes fewer conflicts or loses more pay
    than the plain-cover plan in some week, it keeps the plain-cover plan and adds only rings on top. Returns
    (plan, used_that_fallback)."""
    agents = [c for c in week.conflicts if week.owner[c] in adopters]
    plan = plain_covers(cover_chains(rings(Plan(week), agents, cap, release_passers), adopters, cap), cap)
    if plan.count() >= plain.count() and plan.pay_lost() <= plain.pay_lost():
        return plan, False
    fallback = plain.copy()
    return rings(fallback, [c for c in agents if c not in fallback.fixed], cap, release_passers), True


def group_chat_breaks(week: Week, cap: int | None) -> list[str]:
    """The same group chat with nobody checking limits: the first free coworker who wants hours takes the shift.
    Returns the helper of every cover that broke a limit (the Rulebook would have said no)."""
    plan, out = Plan(week), []
    for c in week.conflicts:
        owner = plan.holder[c]
        for h in week.replies[c]:
            if h != owner and free(plan, h, [c], [], cap):
                if not verdict(plan, h, [c], []).ok:
                    out.append(h)
                plan.held[h].append(c)
                plan.held[owner].remove(c)
                plan.holder[c] = h
                break
    return out


def recheck(plan: Plan) -> list[str]:
    """Independent re-check of every final schedule with rulebook.rules.evaluate and the raw busy blocks."""
    w, problems = plan.week, []
    for pid, p in w.people.items():
        final = [w.shift[s] for s in plan.held[pid]]
        v = evaluate(p.student, final, p.busy, w.monday, added_pay=max(0.0, plan.pay_change(pid)))
        problems += [f"{pid}: {x.rule_id} ({x.detail})" for x in v.findings if x.status == "blocked"]
        for i, s in enumerate(final):
            if s.id not in p.shifts and any(s.hits(b.start, b.end) for b in p.busy):
                problems.append(f"{pid}: took {s.id} while busy")
            if any(s.hits(o.start, o.end) for o in final[i + 1:]):
                problems.append(f"{pid}: double-booked at {s.id}")
    held = Counter(s for v in plan.held.values() for s in v)
    if set(held) != set(w.shift) or max(held.values()) > 1:
        problems.append("a shift was lost or duplicated")
    return problems


# ---- synthetic weeks -----------------------------------------------------------------------------------------------

def _rng(seed: int, *parts: object) -> random.Random:
    return random.Random(":".join(str(x) for x in (seed, *parts)))  # str seeds hash with sha512: stable


def _slots_hit(p: Params, monday: date, start: datetime, end: datetime) -> set[tuple[int, int]]:
    """(weekday, start hour) of every shift slot this week that overlaps [start, end)."""
    out = set()
    for d in range(7):
        for h in p.slot_starts:
            s = at(monday + timedelta(days=d), h)
            if start < s + timedelta(hours=p.shift_hours) and s < end:
                out.add((d, h))
    return out


def make_roster(p: Params, seed: int, i: int, monday: date, in_session: bool) -> Week:
    rng = _rng(seed, "roster", i)
    ids = [f"s{k:02d}" for k in range(p.students)]
    f1 = set(rng.sample(ids, round(p.f1_share * p.students)))
    domestic = [s for s in ids if s not in f1]
    fws = set(rng.sample(domestic, round(p.fws_share * p.students)))
    near_cap = set(rng.sample(sorted(set(domestic) - fws), round(p.near_cap_share * p.students)))
    wants = set(rng.sample(ids, round(p.wants_hours_share * p.students)))
    fri_avoid = set(rng.sample(ids, round(p.fri_evening_avoid_share * p.students)))
    patterns = [(days, minutes, hh, mm) for days, minutes in COURSE_PATTERNS for hh, mm in COURSE_STARTS]
    courses = rng.sample(patterns, p.courses)
    all_slots = [(d, h) for d in range(7) for h in p.slot_starts]

    people, shifts, owner = {}, {}, {}
    for pid in ids:
        enrolled = tuple(sorted(rng.sample(range(p.courses), p.courses_per_student))) if in_session else ()
        busy, cannot = [], set()
        for c in enrolled:
            days, minutes, hh, mm = courses[c]
            for d in days:
                start = at(monday + timedelta(days=d), hh, mm)
                end = start + timedelta(minutes=minutes)
                busy.append(BusyBlock(id=f"{pid}-c{c}-{d}", start=start, end=end, kind="class",
                                      label=f"course {c}", source="class"))
                cannot |= _slots_hit(p, monday, start, end)
        if pid in fri_avoid:
            cannot.add((4, 18))
        other: dict[str, float] = {}
        n = rng.randint(*p.shifts_per_student)
        if pid in f1:
            other = {"other on-campus job": float(rng.randint(*p.f1_other_hours))}
            n = min(n, int(20 - other["other on-campus job"]) // p.shift_hours)
        open_slots = [s for s in all_slots if s not in cannot]
        mine = rng.sample(open_slots, min(n, len(open_slots)))
        if pid in near_cap:
            other = {"second ASU job": float(rng.randint(22, 25) - p.shift_hours * len(mine))}
        usual = p.shift_hours * len(mine) + sum(other.values())
        ceiling = 20 if pid in f1 else 25  # everyone is inside every limit before the week starts
        history = [round(min(ceiling, max(0.0, usual + rng.uniform(-p.history_noise, p.history_noise))), 1)
                   for _ in range(p.history_weeks)]
        limits = Limits(f1_or_j1=pid in f1, fws=pid in fws, other_employer_hours=other, hours_history=history,
                        fws_award_remaining=float(round(rng.uniform(*p.fws_award_remaining))) if pid in fws else None)
        prefs = Preferences(wants_more_hours=pid in wants, soft_avoid=[
            SoftAvoid(weekday=4, start_hour=18, end_hour=22, label="Friday evenings")] if pid in fri_avoid else [])
        sids = []
        for d, h in sorted(mine):
            day = monday + timedelta(days=d)
            sid = f"{pid}-{d}-{h}"
            shifts[sid] = Shift(id=sid, employer="library", start=at(day, h), end=at(day, h + p.shift_hours),
                                wage=p.wage)
            owner[sid] = pid
            sids.append(sid)
        people[pid] = Person(Student(id=pid, name=pid, limits=limits, prefs=prefs), tuple(sids), busy, cannot,
                             {s: rng.random() for s in all_slots}, enrolled)
    return Week(monday, people, shifts, owner, [], {}, rng.sample(ids, len(ids)))


def _add_busy(week: Week, p: Params, pid: str, block: BusyBlock) -> None:
    person = week.people[pid]
    person.busy.append(block)
    person.cannot |= _slots_hit(p, week.monday, block.start, block.end)


def _finish(week: Week, rng: random.Random) -> Week:
    """Conflicts are own shifts that collide with any non-class busy block; set the group-chat order."""
    week.conflicts = [sid for sid, pid in week.owner.items()
                      if any(week.shift[sid].hits(b.start, b.end) for b in week.people[pid].busy if b.kind != "class")]
    rng.shuffle(week.conflicts)
    helpers = sorted(pid for pid, person in week.people.items() if person.wants_hours)
    week.replies = {c: rng.sample(helpers, len(helpers)) for c in week.conflicts}
    return week


def _extra_events(week: Week, p: Params, rng: random.Random) -> None:
    for pid, person in week.people.items():
        own = [week.shift[s] for s in person.shifts]
        for k in range(p.extra_events_per_student):
            for _ in range(10):
                day = week.monday + timedelta(days=rng.randrange(7))
                start = at(day, rng.randint(9, 20))
                end = start + timedelta(hours=rng.choice((2, 3)))
                if not any(s.hits(start, end) for s in own):
                    _add_busy(week, p, pid, BusyBlock(id=f"{pid}-x{k}", start=start, end=end, kind="other",
                                                      label="event", source="calendar"))
                    break


def make_week(p: Params, seed: int, rate: float, i: int) -> Week:
    """An in-session week whose expected conflict rate is `rate`; half the conflicts are clustered exam evenings."""
    week = make_roster(p, seed, i, p.term_monday, in_session=True)
    rng = _rng(seed, "events", rate, i)
    target = sum(rng.random() < rate for _ in week.shift)
    hit: set[str] = set()
    exams = [(c, d) for c in range(p.courses) for d in EXAM_EVES]
    rng.shuffle(exams)
    for c, d in exams:
        if len(hit) >= round(p.clustered_share * target):
            break
        day = week.monday + timedelta(days=d)
        for pid, person in week.people.items():
            if c in person.enrolled:
                _add_busy(week, p, pid, BusyBlock(id=f"{pid}-e{c}-{d}", start=at(day, 18), end=at(day, 22),
                                                  kind="exam", label=f"course {c} exam prep", source="canvas"))
                hit.update(s for s in person.shifts if week.slot(s) == (d, 18))
    rest = sorted(set(week.shift) - hit)
    for sid in rng.sample(rest, max(0, min(len(rest), target - len(hit)))):
        s = week.shift[sid]
        start = s.start + timedelta(hours=rng.randint(0, p.shift_hours - 1))
        _add_busy(week, p, week.owner[sid], BusyBlock(id=f"{sid}-ev", start=start,
                                                      end=start + timedelta(hours=rng.choice((1, 2))),
                                                      kind=rng.choice(EVENT_KINDS), label="event",
                                                      source="calendar"))
    _extra_events(week, p, rng)
    return _finish(week, rng)


def make_break_week(p: Params, seed: int, i: int) -> Week:
    """A winter-break week: no classes, half the domestic students go home, every F-1 student stays and wants hours."""
    monday = p.break_mondays[i % len(p.break_mondays)]
    week = make_roster(p, seed, i, monday, in_session=False)
    rng = _rng(seed, "break", i)
    domestic = sorted(pid for pid, x in week.people.items() if not x.student.limits.f1_or_j1)
    home = set(rng.sample(domestic, round(p.going_home_share * len(domestic))))
    for pid, person in week.people.items():
        if pid in home:
            _add_busy(week, p, pid, BusyBlock(id=f"{pid}-home", start=at(monday, 0),
                                              end=at(monday + timedelta(days=7), 0), kind="vacation",
                                              label="home for the break", source="calendar"))
        wants = pid not in home and (person.wants_hours or person.student.limits.f1_or_j1)
        person.student = person.student.model_copy(update={"prefs": person.student.prefs.model_copy(
            update={"wants_more_hours": wants})})
    _extra_events(week, p, rng)
    return _finish(week, rng)


# ---- one week, many weeks ------------------------------------------------------------------------------------------

ORACLE_MAX_AGENTS = 10  # sim/oracle.py is exhaustive; past ~10 conflicted shifts one week can take minutes


def play_week(p: Params, week: Week) -> tuple[Plan, dict[float, tuple[Plan, bool]], list[str]]:
    cap = p.helper_extra_shifts
    plain = plain_covers(Plan(week), cap)
    tag = {a: tag_out(week, week.adopters(a), cap, plain, p.release_passers) for a in p.adoption}
    return plain, tag, group_chat_breaks(week, cap)


def run_week(p: Params, seed: int, rate: float, i: int) -> dict:
    week = make_week(p, seed, rate, i)
    plain, tag, breaks = play_week(p, week)
    row = {"shifts": len(week.shift), "conflicts": len(week.conflicts), "plain_fixed": plain.count(),
           "plain_pay": plain.pay_lost(), "problems": len(recheck(plain)), "breaks": len(breaks), "oracle": None}
    for a, (plan, fell_back) in tag.items():
        adopters = week.adopters(a)
        row[a] = {"fixed": plan.count(), "pay": plan.pay_lost(), "ring": plan.count("ring"),
                  "chain": plan.count("chain"), "fallback": fell_back, "rings": plan.rings,
                  "prevented": sum(1 for h in breaks if h in adopters), "problems": len(recheck(plan))}
    agents = [c for c in week.conflicts if week.owner[c] in week.adopters(1.0)]
    if len(agents) <= ORACLE_MAX_AGENTS:
        acceptable = {a: set(v) for a, v in swap_prefs(Plan(week), agents, p.helper_extra_shifts).items()}
        row["oracle"] = max_conflicts_solved(acceptable, {a: a for a in agents}, max_len=4)
    return row


def run_break_week(p: Params, seed: int, i: int) -> dict:
    week = make_break_week(p, seed, i)
    cap = p.break_helper_extra_shifts
    plan = plain_covers(Plan(week), cap)  # going-home students can't take a shift back, so only covers apply
    f1 = {pid for pid, x in week.people.items() if x.student.limits.f1_or_j1}
    over_20 = sum(1 for pid in f1 if week_hours(week.people[pid].student, [week.shift[s] for s in plan.held[pid]],
                                                 week.monday) > 20)
    return {"wanted": len(week.conflicts), "handed": plan.count(), "kept": sum(week.shift[c].pay for c in plan.fixed),
            "f1_took": sum(1 for c in plan.fixed if plan.holder[c] in f1), "f1_over_20": over_20,
            "f1": len(f1), "problems": len(recheck(plan)), "unchecked_breaks": len(group_chat_breaks(week, cap))}


def _cell(args: tuple[Params, int, float, range]) -> list[dict]:
    p, seed, rate, weeks = args
    return [run_week(p, seed, rate, i) for i in weeks]


def _breaks(args: tuple[Params, int, range]) -> list[dict]:
    p, seed, weeks = args
    return [run_break_week(p, seed, i) for i in weeks]


def _chunks(n: int, size: int) -> list[range]:
    return [range(k, min(n, k + size)) for k in range(0, n, size)]


def variants(p: Params) -> dict[str, Params]:
    """The assumptions most likely to move the headline, each changed alone at the central conflict rate."""
    return {"helpers take at most 1 extra shift": replace(p, helper_extra_shifts=1),
            "helpers take any number of shifts the rules allow": replace(p, helper_extra_shifts=None),
            "no clustering (every conflict is an individual event)": replace(p, clustered_share=0.0),
            "heavy clustering (80% of conflicts are shared exam evenings)": replace(p, clustered_share=0.8),
            "single TTC pass (passers' shifts stay in the pool)": replace(p, release_passers=False)}


def run_all(p: Params, weeks: int, seed: int, workers: int = 1) -> dict:
    """Every cell of the sweep, the break weeks and the sensitivity runs. Weeks are seeded one by one, so the
    result does not depend on the number of workers."""
    jobs = [(p, seed, r, chunk) for r in p.conflict_rates for chunk in _chunks(weeks, 50)]
    alt = variants(p)
    alt_jobs = [(q, seed, p.central_rate, chunk) for q in alt.values() for chunk in _chunks(weeks, 50)]
    with ProcessPoolExecutor(workers) as pool:
        rows = list(pool.map(_cell, jobs + alt_jobs))
        breaks = [row for part in pool.map(_breaks, [(p, seed, c) for c in _chunks(weeks, 100)]) for row in part]
    out: dict = {"cells": {r: [] for r in p.conflict_rates}, "variants": {k: [] for k in alt}, "break": breaks}
    for (q, _, r, _), part in zip(jobs + alt_jobs, rows, strict=True):
        key = next((k for k, v in alt.items() if v == q), None) if q != p else None
        (out["variants"][key] if key else out["cells"][r]).extend(part)
    return out


# ---- statistics ----------------------------------------------------------------------------------------------------

def mean_ci(xs: list[float]) -> tuple[float, float]:
    """Mean and the half-width of a normal 95% confidence interval over independent weeks."""
    if len(xs) < 2:
        return (xs[0] if xs else 0.0), 0.0
    return statistics.fmean(xs), 1.96 * statistics.stdev(xs) / len(xs) ** 0.5


def pct(rows: list[dict], fixed) -> list[float]:
    return [100 * fixed(r) / r["conflicts"] for r in rows if r["conflicts"]]


def summary(rows: list[dict], a: float) -> dict:
    extra = pct(rows, lambda r: r[a]["fixed"] - r["plain_fixed"])
    sizes = Counter(n for r in rows for n in r[a]["rings"])
    return {
        "rate": mean_ci([100 * r["conflicts"] / r["shifts"] for r in rows]),
        "conflicts": mean_ci([r["conflicts"] for r in rows]),
        "plain": mean_ci(pct(rows, lambda r: r["plain_fixed"])),
        "tag": mean_ci(pct(rows, lambda r: r[a]["fixed"])),
        "extra": mean_ci(extra),
        "extra_p5": sorted(extra)[len(extra) // 20] if extra else 0.0,
        "ring": mean_ci(pct(rows, lambda r: r[a]["ring"])),
        "chain": mean_ci(pct(rows, lambda r: r[a]["chain"])),
        "plain_pay": mean_ci([r["plain_pay"] for r in rows]),
        "tag_pay": mean_ci([r[a]["pay"] for r in rows]),
        "prevented": mean_ci([r[a]["prevented"] for r in rows]),
        "fallback": sum(r[a]["fallback"] for r in rows),
        "problems": sum(r[a]["problems"] + r["problems"] for r in rows),
        "ring_sizes": sizes,
        "weeks": len(rows),
    }


# ---- report --------------------------------------------------------------------------------------------------------

INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
ADOPTION_BLUES = ("#86b6ef", "#3987e5", "#184f95")  # ordinal blue ramp, light to dark (validated, dataviz skill)


def _pm(m: tuple[float, float], unit: str = "%", nd: int = 1) -> str:
    if unit == "$":
        return f"${m[0]:,.0f} ± {m[1]:,.0f}"
    return f"{m[0]:.{nd}f}{unit} ± {m[1]:.{nd}f}"


def _param_rows(p: Params) -> list[tuple[str, str, str]]:
    """(name, value, source) for every Params field, with the source comment read from this file."""
    import inspect
    comments: dict[str, str] = {}
    name = None
    for line in inspect.getsource(Params).splitlines():
        head = line.strip().split(":")[0]
        if line.startswith("    ") and not line.startswith("     ") and head.isidentifier():
            name = head
        if name and "  # " in line and name not in comments:
            comments[name] = line.split("  # ", 1)[1].strip()
    out = []
    for f in fields(p):
        v = getattr(p, f.name)
        if isinstance(v, tuple) and v and isinstance(v[0], date):
            v = ", ".join(d.isoformat() for d in v)
        out.append((f.name, str(v), comments.get(f.name, "")))
    return out


def plot(p: Params, res: dict, weeks: int, path: Path = IMG) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs = [100 * r for r in p.conflict_rates]
    plain = [summary(res["cells"][r], 1.0) for r in p.conflict_rates]
    tag = {a: [summary(res["cells"][r], a) for r in p.conflict_rates] for a in p.adoption}
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": AXIS,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=150, facecolor=SURFACE)
    panels = [("Conflicts fixed (%)", "plain", "tag", "{:.0f}%"), ("Pay lost per week ($)", "plain_pay", "tag_pay",
                                                                   "${:,.0f}")]
    for ax, (title, pk, tk, fmt) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        series = [("Plain covers", INK2, [s[pk] for s in plain])]
        series += [(f"Tag Out, {a:.0%} on it", c, [s[tk] for s in tag[a]])
                   for a, c in zip(p.adoption, ADOPTION_BLUES, strict=True)]
        for label, color, vals in series:
            m = [v[0] for v in vals]
            ax.fill_between(xs, [v[0] - v[1] for v in vals], [v[0] + v[1] for v in vals], color=color, alpha=0.12,
                            linewidth=0)
            ax.plot(xs, m, color=color, linewidth=2, solid_capstyle="round", solid_joinstyle="round", marker="o",
                    markersize=8, markerfacecolor=color, markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        for _, _, vals in (series[0], series[-1]):  # label only the two lines the headline compares
            ax.annotate(fmt.format(vals[-1][0]), (xs[-1], vals[-1][0]), xytext=(8, 0), textcoords="offset points",
                        va="center", color=INK, fontsize=9)
        ax.set_title(title, loc="left", color=INK, fontsize=11, pad=10)
        ax.set_xlabel("Share of shifts that collide with something that week (%)")
        ax.set_xticks(xs)
        ax.set_xlim(xs[0] - 1.5, xs[-1] + 3.5)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
    axes[0].set_ylim(0, 100)
    axes[1].set_ylim(bottom=0)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=4, frameon=False, bbox_to_anchor=(0.005, 0.945),
               labelcolor=INK2)
    fig.suptitle(f"Plain covers vs Tag Out on a synthetic 40-person Library roster ({weeks:,} weeks per point)",
                 x=0.01, ha="left", color=INK, fontsize=12)
    fig.text(0.01, 0.01, "Bands: 95% confidence interval. " + FOOTER, color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def report(p: Params, res: dict, weeks: int, seed: int, took: float, workers: int) -> str:
    cells = res["cells"]
    central = summary(cells[p.central_rate], 1.0)
    every = {(r, a): summary(cells[r], a) for r in p.conflict_rates for a in p.adoption}
    worst_key = min(every, key=lambda k: every[k]["extra"][0])
    worst = every[worst_key]
    low = every[(p.central_rate, p.adoption[0])]
    go = central["extra"][0] >= p.go_points
    ci_low = central["extra"][0] - central["extra"][1]
    rate, adopt = f"{p.central_rate:.0%}", f"{p.adoption[-1]:.0%}"
    alt = {k: summary(rows, 1.0) for k, rows in res["variants"].items()}
    under = [f"{k} ({v['extra'][0]:.1f})" for k, v in alt.items() if v["extra"][0] < p.go_points]
    moves = "; ".join(f"{k}: {v['extra'][0]:.1f}" for k, v in alt.items())
    pay_cut = 100 * (1 - central["tag_pay"][0] / central["plain_pay"][0]) if central["plain_pay"][0] else 0.0
    L: list[str] = ["# Simulation: plain covers vs Tag Out rings and chains", ""]

    if go:
        L.append(f"**Go/no-go: go.** At a {rate} conflict rate with {adopt} of the roster on Tag Out, rings and "
                 f"chains fix {central['extra'][0]:.1f} percentage points more of the week's conflicts than plain "
                 f"covers (95% CI ± {central['extra'][1]:.1f}), above the {p.go_points:g}-point bar in "
                 "docs/DESIGN.md section 7. Rings can lead the pitch."
                 + (f" The lower end of the confidence interval ({ci_low:.1f}) is under {p.go_points:g}, so the "
                    "margin is thin." if ci_low < p.go_points else "")
                 + (" The margin depends on assumptions: changed one at a time, these push it under "
                    f"{p.go_points:g} points: " + "; ".join(under) + " (see Sensitivity)." if under else ""))
    elif central["extra"][0] + central["extra"][1] >= p.go_points:
        lo, hi = central["extra"][0] - central["extra"][1], central["extra"][0] + central["extra"][1]
        L.append(f"**Go/no-go: borderline.** At a {rate} conflict rate with {adopt} of the roster on Tag Out, "
                 f"rings and chains add {central['extra'][0]:.2f} percentage points over plain covers (95% CI "
                 f"{lo:.1f} to {hi:.1f}). The {p.go_points:g}-point bar in docs/DESIGN.md section 7 sits inside "
                 "that interval, so the simulation neither clears it nor misses it with confidence. "
                 "Recommendation: lead with the Sunday check, plain covers and the pay that trades save (below), "
                 "and present rings as the reason that pay is saved rather than as a bigger fix rate.")
        L += ["", f"What rings and chains clearly change is pay: in the same scenario pay lost per week falls from "
              f"${central['plain_pay'][0]:,.0f} to ${central['tag_pay'][0]:,.0f} ({pay_cut:.0f}% less), because a "
              "swap fixes a conflict without anyone losing the shift. The points figure moves with the assumptions; "
              f"changed one at a time (see Sensitivity): {moves}."]
    else:
        L.append(f"**Go/no-go: no-go on rings as the headline.** At a {rate} conflict rate with {adopt} of the "
                 f"roster on Tag Out, rings and chains add {central['extra'][0]:.1f} percentage points over plain "
                 f"covers (95% CI ± {central['extra'][1]:.1f}), under the {p.go_points:g}-point bar in "
                 "docs/DESIGN.md section 7. Recommendation: lead with \"Sunday check + plain covers + Winter Break "
                 "Handoff\" and show rings as a bonus.")
        L += ["", f"What rings and chains do change is pay: in the same scenario pay lost per week falls from "
              f"${central['plain_pay'][0]:,.0f} to ${central['tag_pay'][0]:,.0f} ({pay_cut:.0f}% less), because a "
              "swap fixes a conflict without anyone losing the shift. The points figure moves with the assumptions; "
              f"changed one at a time (see Sensitivity): {moves}."]
    L += ["",
          f"- Typical case ({rate} conflicts, {adopt} adoption, {central['weeks']:,} weeks): plain covers fix "
          f"{_pm(central['plain'])} of conflicts; Tag Out fixes {_pm(central['tag'])}; rings and chains add "
          f"{_pm(central['extra'], ' points')}. Pay lost per week drops from {_pm(central['plain_pay'], '$')} to "
          f"{_pm(central['tag_pay'], '$')}.",
          "- Worst case, same scenario: "
          + (f"the worst 5% of weeks get {central['extra_p5']:.1f} extra points or fewer"
             if central["extra_p5"] > 0 else "in at least 1 week in 20, rings and chains add nothing")
          + ". Tag Out never fixes fewer than plain covers, because the broker keeps the plain-cover plan when that "
          "plan is better.",
          f"- Worst case in the whole sweep: {worst_key[0]:.0%} conflicts with {worst_key[1]:.0%} adoption, where "
          f"rings and chains add {_pm(worst['extra'], ' points')}. At {rate} conflicts with only "
          f"{p.adoption[0]:.0%} of the roster on Tag Out they add {_pm(low['extra'], ' points')}: rings need most "
          "of a roster on board.",
          f"- Pitch line (synthetic): \"In our simulation of a 40-person roster, plain covers fixed "
          f"{central['plain'][0]:.0f}% of conflicts; trades fixed {central['extra'][0]:.0f} percentage points "
          f"more, and students lost {pay_cut:.0f}% less pay.\"",
          "",
          f"![Conflicts fixed and pay lost by conflict rate and adoption](img/{IMG.name})", ""]

    L += ["## Conflicts fixed", "",
          "Mean ± 95% confidence interval over the simulated weeks, as a share of each week's conflicts. "
          "\"Extra\" is Tag Out minus plain covers in the same week, in percentage points. The last two columns "
          "say how Tag Out fixed them: many ring and chain fixes are conflicts a plain cover would also have "
          "fixed, but with the owner losing the pay (next table).", "",
          "| Conflict rate (measured) | Conflicts / week | On Tag Out | Plain covers fix | Tag Out fixes | Extra "
          "(points) | Fixed by a ring | Fixed by a chain |",
          "|---|---|---|---|---|---|---|---|"]
    for r in p.conflict_rates:
        for a in p.adoption:
            s = every[(r, a)]
            L.append(f"| {r:.0%} ({s['rate'][0]:.1f}%) | {s['conflicts'][0]:.1f} | {a:.0%} | {_pm(s['plain'])} | "
                     f"{_pm(s['tag'])} | {_pm(s['extra'], '')} | {_pm(s['ring'])} | {_pm(s['chain'])} |")
    L += ["", "## Pay lost and rule breaks", "",
          f"Pay lost is what students lose when their shift moves to someone else and they take nothing back "
          f"(one shift = {p.shift_hours} h × ${p.wage:g} = ${p.shift_hours * p.wage:g}). A conflict nobody fixes "
          "is not counted as pay lost: the student either works it anyway or calls out, and the model doesn't "
          "pick. Rule breaks prevented: covers an unchecked group chat would make (first free coworker who wants "
          "hours takes it) that break a limit, where that coworker is on Tag Out and their mascot says no.", "",
          "| Conflict rate | On Tag Out | Pay lost / week, plain covers | Pay lost / week, Tag Out | Rule breaks "
          "prevented / week | Weeks Tag Out kept the plain plan |",
          "|---|---|---|---|---|---|"]
    for r in p.conflict_rates:
        for a in p.adoption:
            s = every[(r, a)]
            L.append(f"| {r:.0%} | {a:.0%} | {_pm(s['plain_pay'], '$')} | {_pm(s['tag_pay'], '$')} | "
                     f"{_pm(s['prevented'], '', 2)} | {s['fallback']} of {s['weeks']} |")
    problems = sum(s["problems"] for s in every.values())
    L += ["", f"Every final schedule in every plan was re-checked with `rulebook.rules.evaluate` and against each "
          f"student's raw busy blocks: {problems} accepted moves broke a limit or double-booked anyone.", ""]

    b = res["break"]
    per = {k: mean_ci([row[k] for row in b])
           for k in ("wanted", "handed", "kept", "f1_took", "f1_over_20", "f1", "unchecked_breaks")}
    n_break = len(p.break_mondays)
    break_problems = sum(row["problems"] for row in b)
    L += ["## Winter Break Handoff", "",
          f"{len(b):,} simulated winter-break weeks (Mon {p.break_mondays[0]:%b %d %Y} to Sun "
          f"{p.break_mondays[-1] + timedelta(days=6):%b %d %Y}, {n_break} weeks; F-1 limit {40} h in these weeks "
          f"per config/rules.yaml). {p.going_home_share:.0%} of domestic students go home and want every shift "
          "gone; every F-1 student stays and wants hours, as do domestic students who stay and wanted more hours. "
          f"Everyone is on Tag Out. Helpers take at most {p.break_helper_extra_shifts} extra shifts a week "
          "(assumption).", "",
          "| Per break week | Mean ± 95% CI |", "|---|---|",
          f"| Shifts going-home students want gone | {_pm(per['wanted'], '')} |",
          f"| Shifts handed off | {_pm(per['handed'], '')} ({100 * per['handed'][0] / per['wanted'][0]:.0f}%) |",
          f"| of which F-1 students took | {_pm(per['f1_took'], '')} |",
          f"| F-1 students over 20 h that week (legal only in a listed break week) | "
          f"{_pm(per['f1_over_20'], '')} of {per['f1'][0]:.0f} |",
          f"| Dollars kept on campus (pay earned by students who stayed) | {_pm(per['kept'], '$')} |",
          f"| Rule breaks in accepted handoffs | {break_problems} in {len(b):,} weeks |",
          f"| Rule breaks an unchecked group chat would make | {_pm(per['unchecked_breaks'], '', 2)} |", "",
          f"Over the whole {n_break}-week break that is about {n_break * per['handed'][0]:.0f} shifts handed off "
          f"and ${n_break * per['kept'][0]:,.0f} kept on campus for one 40-person roster, with "
          f"{break_problems} rule breaks. The number handed off is set mostly by how many extra shifts the people "
          f"who stay will take ({p.break_helper_extra_shifts}, an assumption); a higher cap hands off more. In "
          "break weeks there is nothing to trade back (the people leaving can't take a shift), so this is "
          "matching plus the private limit check, not rings.", ""]

    with_oracle = {r: [row for row in cells[r] if row["oracle"] is not None] for r in p.conflict_rates}
    L += ["## TTC compared with the best possible rings", "",
          "`sim/oracle.py` (`max_conflicts_solved`) searches every set of disjoint rings of up to 4 shifts that "
          "everyone in them would accept, before any covers. It is exhaustive, so it runs only in weeks with at "
          f"most {ORACLE_MAX_AGENTS} conflicted shifts on Tag Out ({adopt} adoption). TTC can also close rings "
          "longer than 4, so in a few weeks it can beat this bound. TTC follows each person's ranked picks "
          "instead of maximising the count, so it can fix fewer than the bound; passers leave with their own "
          "shift and the rest re-point (standard TTC with outside options). The sensitivity row \"single TTC "
          "pass\" shows what that release is worth.", "",
          "| Conflict rate | Weeks with the bound | TTC ring fixes / week | Best rings of <= 4 / week |",
          "|---|---|---|---|"]
    for r in p.conflict_rates:
        rows = with_oracle[r]
        if rows:
            L.append(f"| {r:.0%} | {len(rows):,} of {len(cells[r]):,} | "
                     f"{_pm(mean_ci([row[1.0]['ring'] for row in rows]), '', 2)} | "
                     f"{_pm(mean_ci([row['oracle'] for row in rows]), '', 2)} |")
        else:
            L.append(f"| {r:.0%} | 0 of {len(cells[r]):,} | - | - |")
    sizes = central["ring_sizes"]
    total_rings = sum(sizes.values())
    L += ["", f"Ring sizes at {rate} conflicts, {adopt} adoption: "
          + ", ".join(f"{n} people: {c:,}" for n, c in sorted(sizes.items()))
          + (f" ({100 * sum(c for n, c in sizes.items() if n > 4) / total_rings:.0f}% longer than 4)."
             if total_rings else "."), ""]

    L += ["## Sensitivity", "",
          f"Each row changes one assumption, at {rate} conflicts and {adopt} adoption, same seeds.", "",
          "| Change | Plain covers fix | Tag Out fixes | Extra (points) |", "|---|---|---|---|",
          f"| none (the model above) | {_pm(central['plain'])} | {_pm(central['tag'])} | "
          f"{_pm(central['extra'], '')} |"]
    for k, rows in res["variants"].items():
        s = summary(rows, 1.0)
        L.append(f"| {k} | {_pm(s['plain'])} | {_pm(s['tag'])} | {_pm(s['extra'], '')} |")

    L += ["", "## How one week is played", "",
          "1. A fresh roster: 40 students, each with classes, 2-4 Library shifts that avoid their classes, an "
          "8-week hours history, and private limits (F-1 20 h across all on-campus jobs, 25 h average, FWS award, "
          "40 h week). Then the week's life events: shared-course exam evenings (clustered) and individual "
          "events, calibrated so the expected share of shifts that collide equals the conflict rate. A shift "
          "never collides with its owner's class; classes only stop people taking other shifts.",
          "2. **Plain covers** (the baseline, no Tag Out): conflicts go to the group chat in a random order; "
          "coworkers who want hours answer in a random order; the first one who is free and passes "
          "`check_change(add=[shift])` takes it. The owner loses that pay.",
          "3. **Tag Out**: each conflicted shift owned by an adopter is one TTC agent. Its picks are the other "
          "conflicted adopters' shifts its owner is free for, would take, and that pass "
          "`check_change(add=[pick], drop=[own])`, ranked by the owner's private slot preference. "
          "`broker.ttc.ttc` closes rings. Then `broker.ttc.chains` builds cover chains from what is left: helpers "
          "are adopters who want hours; a covered owner may take another open shift hours-neutral. Then plain "
          "covers handle everything still open, including every non-adopter's conflict. Every ring and chain is "
          "re-checked as a whole before it commits; one no drops it (a chain falls back to a shorter one).",
          "4. The broker never proposes a plan worse than plain covers: in a week where rings-first fixes fewer "
          "conflicts or loses more pay than the plain-cover plan, it keeps the plain-cover plan and adds only "
          "rings among the conflicts left over. The tables count those weeks.",
          "5. Every final schedule is re-checked with `rulebook.rules.evaluate`.", "",
          "## Model and assumptions", "",
          "All parameters live in one dataclass, `Params`, at the top of `sim/simulate.py`.", "",
          "| Parameter | Value | Source or assumption |", "|---|---|---|"]
    L += [f"| `{n}` | {v} | {c} |" for n, v, c in _param_rows(p)]
    L += ["", "Limits of this model:",
          "- Synthetic students and calendars. The survey numbers are not in yet; the conflict rate is swept "
          "instead of measured.",
          "- One employer, one role, equal shifts and wages. Other employers' hours count toward limits but their "
          "shifts can't be traded.",
          "- Everyone answers. Nobody declines a ring at the confirm step, and no manager rejects one.",
          "- Who is on Tag Out is random. Real adoption would cluster in friend groups and shared shifts.",
          "- Weeks are independent; hours history doesn't carry from one simulated week to the next.", "",
          "## Reproduce", "",
          "```",
          f"python -m sim.simulate --weeks {weeks} --seed {seed}",
          "```", "",
          f"{weeks:,} weeks per cell, seed {seed}, {workers} worker processes, {took:.0f} s. Every week is seeded "
          "on its own, so the numbers do not depend on the worker count.", "",
          "---", "", FOOTER, ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--weeks", type=int, default=1000, help="weeks per cell (default 1000)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()
    p = Params()
    t0 = time.perf_counter()
    res = run_all(p, args.weeks, args.seed, args.workers)
    took = time.perf_counter() - t0
    plot(p, res, args.weeks)
    DOC.write_text(report(p, res, args.weeks, args.seed, took, args.workers), encoding="utf-8")
    c = summary(res["cells"][p.central_rate], 1.0)
    b = res["break"]
    winter = {k: mean_ci([row[k] for row in b])[0] for k in ("wanted", "handed", "kept", "unchecked_breaks")}
    (DOC.parent / "simulation.json").write_text(json.dumps({
        "weeks": args.weeks, "seed": args.seed, "roster": 40, "conflict_rate": p.central_rate,
        "plain_pct": round(c["plain"][0], 1), "tagout_pct": round(c["tag"][0], 1),
        "extra_points": round(c["extra"][0], 1), "extra_ci": round(c["extra"][1], 1),
        "plain_pay_lost": round(c["plain_pay"][0]), "tagout_pay_lost": round(c["tag_pay"][0]),
        "winter": {"wanted": round(winter["wanted"], 1), "handed": round(winter["handed"], 1),
                   "kept": round(winter["kept"]), "rule_breaks": sum(row["problems"] for row in b),
                   "unchecked_breaks": round(winter["unchecked_breaks"], 2)},
    }, indent=1), encoding="utf-8")
    print(f"plain covers {c['plain'][0]:.1f}%, Tag Out {c['tag'][0]:.1f}%, +{c['extra'][0]:.1f} points "
          f"({took:.0f} s) -> {DOC.relative_to(ROOT)}, {IMG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
