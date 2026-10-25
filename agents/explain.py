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
from rulebook.rules import f1_cap_for, week_hours

SOURCE_WORDS = {"canvas": "Canvas", "calendar": "your calendar", "gmail": "an email", "text": "your text", "asu": "ASU's calendar",
                "class": "your class schedule", "seed": "your calendar"}

SYSTEM = ("You rewrite one short text message from a student's scheduling assistant so it sounds natural and kind, "
          "like a friend texting. Keep every number, time, day and name exactly. No emoji. Under 45 words. "
          "Return only the message.")


def polish(text: str) -> str:
    if os.environ.get("TAGOUT_LLM_EXPLAIN") != "1" or "\n" in text:  # structured texts stay as written
        return text
    out = llm.call_text(llm.EXPLAIN_MODEL, SYSTEM, text)
    if not out:
        return text
    tokens = set(re.findall(r"\$?\d+(?::\d\d)?|Mon|Tue|Wed|Thu|Fri|Sat|Sun", text))
    if not tokens <= set(re.findall(r"\$?\d+(?::\d\d)?|Mon|Tue|Wed|Thu|Fri|Sat|Sun", out)):
        return text  # the model dropped or changed a fact: keep the template
    return out


def intro(st: Student) -> str:
    """The first message in a newly linked chat: what the mascot does, what it knows, what leaves it."""
    other = ", ".join(st.limits.other_employer_hours) or "none"
    return (f"Hi {st.name}, I'm your Tag Out mascot.\n\n"
            "Every Sunday at 6 PM I check next week's Library shifts against your Canvas, your calendar and what "
            "you text me. I only text you when a shift collides with something.\n\n"
            f"What I know, privately: your shifts, your calendar, other jobs ({other}) and the work-hour limits "
            "that apply to you. What your coworkers and manager see: that you're busy at some times, which shift "
            "you want to trade, and your yes or no answers. Never why, and never your hours at other jobs.\n\n"
            "Text me anytime, for example:\n"
            "- dentist Thu 3pm\n"
            "- I'm sick, can't make it today\n"
            "- I want more hours this week\n"
            "- set up a meeting with my supervisor\n"
            "- the printer at the desk is broken")


def collision(name: str, c: Collision) -> str:
    src = SOURCE_WORDS.get(c.source, c.source)
    return (f"Sunday check for the week of {c.week_of:%b} {c.week_of.day}: one shift needs a look.\n\n"
            f"Your Library shift {c.shift_label} overlaps {c.busy_label} (I found it in {src}).\n\n"
            "Find a trade: I'll ask your coworkers' mascots for a swap first, so you keep your hours and pay. If no "
            "swap works, someone may cover it. They only see the shift, never why, and nothing moves until you "
            "confirm.\n"
            "Not now: you keep the shift.")


def ask(shift_label: str, avoid_label: str) -> str:
    return ("A trade can close if you say yes.\n\n"
            f"You'd take a Library shift on {shift_label}. That's your {avoid_label} slot, which you asked me to "
            "keep free, so I won't decide for you.\n\n"
            "Take it: the swap can close and you keep your pay this week.\n"
            "Keep my slot: I pass, and nobody is told why.")


def fws_runway(lasts: float, paid: float, weeks_left: int, remaining: float) -> str:
    span = "only this week" if lasts < 1.5 else f"about {lasts:.0f} more weeks"
    return (f"Heads up: you're scheduled for ${paid:.0f} this week, so the ${remaining:.0f} left on your Work-Study "
            f"award covers {span}, and the next break is {weeks_left} weeks away. Ask your supervisor or Financial "
            "Aid now what happens when it runs out. I won't take extra shifts that go past it.")


def ask_limit(shift_label: str, hours: float, cap: float, other: dict[str, float] | None = None) -> str:
    check = "".join(f" Is it still {h:g} h at {job} this week? If it's more, choose Leave room." for job, h in
                    (other or {}).items())
    return (f"A {shift_label} Library shift could come to you, but it would put you at {hours:g} of your {cap:g} "
            "on-campus hours this week (your F-1 limit counts every campus job together). That leaves no room to "
            f"stay late or cover a call-out.{check}\n\n"
            "Leave room: I pass. This is the safer choice.\n"
            "Take it: only if you're sure your week won't run over.")


def confirm(st: Student, adds: list[Shift], drops: list[Shift], moves: list[Move], names: dict[str, str],
            shifts: list[Shift], busy: list[BusyBlock], approver: str | None = None) -> str:
    who = {m.shift_id: names.get(m.to_agent, m.to_agent) for m in moves}
    owner = {m.shift_id: "an extra shift your manager posted" if m.from_agent == "open"
             else f"from {names.get(m.from_agent, m.from_agent)}" for m in moves}
    lines = ["Here's a trade. Nothing has moved yet.", ""]
    for d in drops:
        lines.append(f"You give: {d.label} ({who.get(d.id, 'someone')} takes it)")
    for a in adds:
        lines.append(f"You get: {a.label} ({owner.get(a.id, 'from a coworker')})")
    pay = sum(a.pay for a in adds) - sum(d.pay for d in drops)
    if adds and drops and pay == 0:
        lines.append(f"Pay this week: you keep your ${drops[0].pay:.0f}.")
    elif pay > 0:
        lines.append(f"Pay this week: +${pay:.0f}.")
    elif pay < 0:
        lines.append(f"Pay this week: you give up ${-pay:.0f}.")
    if st.limits.f1_or_j1 and (adds or drops):
        monday = week_start((adds or drops)[0].start.date())
        after = [s for s in shifts if s.id not in {d.id for d in drops}] + adds
        other = ", ".join(f"{h:g} h at {k}" for k, h in st.limits.other_employer_hours.items())
        lines.append(f"Hours: you'd be at {week_hours(st, after, monday):g} of your {f1_cap_for(st, monday):g} hours "
                     "across all on-campus jobs" + (f", counting the {other} you told me about." if other else "."))
    rest = (f"The {approver.lower()} arranged it, so it goes through as soon as both of you confirm."
            if approver else "It goes through only if everyone in it confirms and your manager approves it (swaps "
            "can also pass on their standing rule for swaps).")
    lines += ["I checked it against your limits privately. Nobody else sees your numbers.", "",
              rest + " Confirm, or Decline (nobody is told why)."]
    return "\n".join(lines)


def committed(adds: list[Shift], drops: list[Shift], week: list[Shift] | None = None,
              approver: str | None = None) -> str:
    lines = [f"Done. The cover went through: both of you confirmed, and the {approver.lower()} arranged it." if approver
             else "Done. The trade went through: everyone in it confirmed, and your manager approved it (or their "
             "standing rule for swaps did).", ""]
    lines += [f"You gave: {d.label}" for d in drops] + [f"You took: {a.label}" for a in adds]
    if week:
        jobs = {s.employer for s in week}
        employer = {"library": "Library ", "dining": "Dining ", "rec center": "Rec center "}.get(jobs.pop(), "") \
            if len(jobs) == 1 else ""
        lines.append(f"Your {employer}week now: "
                     + ", ".join(s.label for s in sorted(week, key=lambda s: s.start)) + ".")
    aramark = any(s.employer == "dining" for s in adds + drops)  # Aramark keeps its own time records, not Workday
    lines += ["", "Record your time the way Aramark has you do it for that shift." if aramark
              else "Enter your time in Workday as usual for the shifts you work."]
    return "\n".join(lines)


def aborted() -> str:
    return ("That trade was cancelled before anything changed. Your shifts are exactly as they were.\n\n"
            "Someone's week changed or someone said no. Nobody is told why. I'll keep looking in the next round.")


def issue_draft(text: str, category: str) -> str:
    safety = ("Safety reports also go straight to ASU Environmental Health and Safety, so someone outside your "
              "department sees it at once.\n") if category == "safety" else ""
    return (f"Here's the report I'd send your manager ({category}):\n\n\"{text}\"\n\n"
            "Send with my name: they can reply and follow up with you.\n"
            "Send anonymously: they see the report, not who sent it.\n" + safety +
            "Nothing else from your week goes with it.")


def question_draft(text: str) -> str:
    return ("That's a visa question, and I don't answer those: your DSO at ISSC (the international students office) "
            f"does. I can send them just your question, in your words:\n\n\"{text}\"\n\n"
            "Your hours, jobs and calendar stay with me. Send it?")


def meeting_options(slots: list[tuple]) -> str:
    return ("Here are times next week that work for you and your manager. I only sent your manager the times "
            "you're free, never what you're busy with. Pick one and I'll book it.")


def invite(title: str, when: str, clash: str | None) -> str:
    base = f"Your manager set a {title}: {when}. Only your answer goes back, never a reason."
    if clash:
        return base + f"\n\nHeads up: that's during {clash}."
    return base + "\n\nYou're free then. Add it to your week?"


def week_summary(name: str, monday: date, fixed: int, total: int) -> str:
    return f"Week of {monday:%b %d}: {fixed} of {total} collisions fixed."
