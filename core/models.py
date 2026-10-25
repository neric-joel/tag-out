"""Private domain models. These live inside one mascot and never cross the wire."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.timeutil import fmt_span, overlaps

BusyKind = Literal["class", "exam", "due", "appointment", "interview", "vacation", "protected", "other"]


class _Private(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Shift(_Private):
    """A shift on an employer roster. The roster itself is shared inside the employer."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    employer: str
    role: str = "desk"
    start: datetime
    end: datetime
    wage: float = 16.0

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600

    @property
    def pay(self) -> float:
        return round(self.hours * self.wage, 2)

    @property
    def label(self) -> str:
        return fmt_span(self.start, self.end)

    def hits(self, start: datetime, end: datetime) -> bool:
        return overlaps(self.start, self.end, start, end)


class BusyBlock(_Private):
    """Something in the student's life. `label` and `kind` are private; only "busy" can ever leave."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    start: datetime
    end: datetime
    kind: BusyKind
    label: str
    source: Literal["canvas", "calendar", "gmail", "text", "asu", "class", "seed"]


class SoftAvoid(_Private):
    """A preference, not a rule: the mascot asks its student before trading into one."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    weekday: int  # 0 = Monday
    start_hour: int
    end_hour: int
    label: str


class Preferences(_Private):
    wants_more_hours: bool = False
    never_weekdays: list[int] = Field(default_factory=list)
    protect_exam_eves: bool = True
    soft_avoid: list[SoftAvoid] = Field(default_factory=list)
    accepts_drop: bool = True  # fine losing the pay if nothing else works


class Limits(_Private):
    """The student's private numbers. One code path for everyone; F-1 is just a flag here."""

    f1_or_j1: bool = False
    fws: bool = False
    fws_award_remaining: float | None = None  # left on the award at the start of the week
    other_employer_hours: dict[str, float] = Field(default_factory=dict)  # per week, e.g. {"dining": 9}
    non_asu_employers: list[str] = Field(default_factory=list)  # e.g. ["dining"]: Aramark counts for F-1, not the ASU 25 h
    hours_history: list[float] | None = None  # ASU hours per Mon-Sun week (Workday time)
    hours_history_weeks: list[date] | None = None  # the Monday of each week in hours_history
    hire_date: date | None = None  # Workday hire date: starts the 25 h average's initial 12-month period
    f1_continuing: bool | None = None  # enrolled for the next term: needed for 40 h in a break week (unknown = 20)
    program_end: date | None = None  # program completion date: no on-campus work after it


class Student(_Private):
    id: str
    name: str
    pet_id: str = "debug-duck-v2"
    job_profiles: list[str] = Field(default_factory=lambda: ["desk"])  # Workday job profile(s) they can work
    limits: Limits = Field(default_factory=Limits)
    prefs: Preferences = Field(default_factory=Preferences)


class Collision(_Private):
    shift_id: str
    shift_label: str
    busy_id: str
    busy_label: str
    busy_kind: BusyKind
    source: str
    week_of: date
