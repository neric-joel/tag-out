"""Texts a mascot sends its own student. Templates first; Claude Sonnet may rephrase, but only if every number
and shift label survives (otherwise the template is used). Rule decisions are never made here.
"""

from __future__ import annotations

import os
import re
from datetime import date

from core.models import BusyBlock, Collision, Shift, Student
from core.timeutil import week_start
from core.wire import Move
from ingest import llm
from rulebook.rules import week_hours

SOURCE_WORDS = {"canvas": "Canvas", "calendar": "your calendar", "text": "your text", "asu": "ASU's calendar",
                "class": "your class schedule", "seed": "your calendar"}

SYSTEM = ("You rewrite one short text message from a student's scheduling assistant so it sounds natural and kind, "
          "like a friend texting. Keep every number, time, day and name exactly. No emoji. Under 45 words. "
          "Return only the message.")


def polish(text: str) -> str:
    if os.environ.get("TAGOUT_LLM_EXPLAIN") != "1":
        return text
    out = llm.call_text(llm.EXPLAIN_MODEL, SYSTEM, text)
    if not out:
        return text
    tokens = set(re.findall(r"\$?\d+(?::\d\d)?|Mon|Tue|Wed|Thu|Fri|Sat|Sun", text))
    if not tokens <= set(re.findall(r"\$?\d+(?::\d\d)?|Mon|Tue|Wed|Thu|Fri|Sat|Sun", out)):
        return text  # the model dropped or changed a fact: keep the template
    return out


def collision(name: str, c: Collision) -> str:
    src = SOURCE_WORDS.get(c.source, c.source)
    return polish(f"Your {c.shift_label} Library shift hits {c.busy_label} (from {src}). "
                  f"Want me to find a trade that keeps your hours?")


def ask(shift_label: str, avoid_label: str) -> str:
    return polish(f"A {shift_label} Library shift could come to you in a trade, but that's your {avoid_label} "
                  f"slot. Take it so you keep your pay this week?")


def confirm(st: Student, adds: list[Shift], drops: list[Shift], moves: list[Move], names: dict[str, str],
            shifts: list[Shift], busy: list[BusyBlock]) -> str:
    who = {m.shift_id: names.get(m.to_agent, m.to_agent) for m in moves}
    owner = {m.shift_id: names.get(m.from_agent, m.from_agent) for m in moves}
    parts = []
    for d in drops:
        parts.append(f"{who.get(d.id, 'Someone')} takes your {d.label}.")
    for a in adds:
        parts.append(f"You take {owner.get(a.id, 'a')}'s {a.label}.")
    pay = sum(a.pay for a in adds) - sum(d.pay for d in drops)
    if adds and drops and pay == 0:
        parts.append(f"You keep your ${drops[0].pay:.0f}.")
    elif pay > 0:
        parts.append(f"That's +${pay:.0f} this week.")
    elif pay < 0:
        parts.append(f"You give up ${-pay:.0f} this week.")
    if st.limits.f1_or_j1 and (adds or drops):
        monday = week_start((adds or drops)[0].start.date())
        after = [s for s in shifts if s.id not in {d.id for d in drops}] + adds
        parts.append(f"You'd be at {week_hours(st, after, monday):g} of your 20 hours across all jobs.")
    return polish(" ".join(parts) + " Confirm?")


def committed(adds: list[Shift], drops: list[Shift]) -> str:
    bits = [f"gave {d.label}" for d in drops] + [f"took {a.label}" for a in adds]
    return polish("Done. The trade went through: you " + " and ".join(bits) + ". Your manager approved it.")


def aborted() -> str:
    return "That trade was cancelled before anything changed. Your shifts are exactly as they were."


def week_summary(name: str, monday: date, fixed: int, total: int) -> str:
    return f"Week of {monday:%b %d}: {fixed} of {total} collisions fixed."
