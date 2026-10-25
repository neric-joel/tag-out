"""Text intake: "dentist Thu 3pm", "I got the Amazon interview Thu 2pm", "never schedule me Fridays".

Claude Haiku turns a student's text into events and preferences through a strict tool schema. A regex parser is the
fallback and the test oracle. The event's label stays inside the mascot; only "busy" ever leaves.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from core.models import BusyBlock
from core.timeutil import DAY_NAMES, PHX
from ingest import llm
from ingest.ics import _bid, classify

KINDS = ["class", "exam", "due", "appointment", "interview", "vacation", "protected", "other"]

TOOL = {
    "name": "record_week_items",
    "description": "Record calendar events and scheduling preferences found in a student's text message.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string", "description": "short private label, e.g. 'Amazon interview'"},
                        "kind": {"type": "string", "enum": KINDS},
                        "date": {"type": "string", "description": "YYYY-MM-DD, resolved against the reference week"},
                        "start": {"type": "string", "description": "HH:MM 24h"},
                        "end": {"type": "string", "description": "HH:MM 24h; guess a typical length if unstated"},
                    },
                    "required": ["title", "kind", "date", "start", "end"],
                },
            },
            "preferences": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "wants_more_hours": {"type": ["boolean", "null"]},
                    "never_weekdays": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}},
                },
                "required": ["wants_more_hours", "never_weekdays"],
            },
        },
        "required": ["events", "preferences"],
    },
}

SYSTEM = (
    "You read short texts a college student sends to their scheduling assistant and extract calendar events and "
    "work-shift preferences. Resolve weekday names to dates inside the reference week (Monday to Sunday). "
    "Times are America/Phoenix. If no end time is given, use 1 hour for interviews and appointments, 3 hours for "
    "career fairs, and the whole stated range when a range like '1-4' is given (1-4 means 13:00-16:00 unless am "
    "is written). Do not invent events that are not in the text. Weekday numbers: 0=Monday ... 6=Sunday."
)

DAY_RE = re.compile(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b", re.I)
RANGE_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–to]+\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
NEVER_RE = re.compile(r"\b(never|no|not)\b.*\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*s?\b", re.I)


CALLOUT_RE = re.compile(
    r"\b(tag me out|call(?:ing)? out|call in sick|"
    r"(?:can'?t|cannot|can not|won'?t) (?:make|work|do|come to|come in) (?:it|my|the|today|tomorrow|in)|"
    r"cover (?:for )?me|cover my|take my (?:\w+ )?shift|skip my (?:\w+ )?shift|i'?m sick|i am sick|"
    r"not feel(?:ing)? well|feel(?:ing)? (?:sick|ill)|got sick|woke up sick|family emergency)\b",
    re.I)
RELATIVE_RE = re.compile(r"\b(today|tonight|tomorrow)\b", re.I)
# "I'm not calling out", "no need to cover my shift": a call-out phrase right after a negation doesn't count
NEGATED_RE = re.compile(r"\b(?:not|never|no need to|don'?t|won'?t|doesn'?t)\b(?:\s+[\w']+){0,3}\s*$", re.I)
# texts often skip the "?": "can I do CPT next summer", "am I allowed to work during OPT"
ASKS_RE = re.compile(r"^\s*(?:can|could|may|am|is|are|do|does|will|would|should|how|what|when)\b|\bwondering\b",
                     re.I)


ISSUE_RE = re.compile(
    r"\b(broken|not working|(?:isn'?t|doesn'?t|won'?t) work(?:ing)?|jammed|out of (?:paper|toner|order)|"
    r"leak(?:ing|s)?|unsafe|blocked|spill(?:ed)?|report (?:an? )?(?:issue|problem)|problem with)\b", re.I)
# a question about visa status goes to ISSC, never answered by the mascot
VISA_RE = re.compile(r"\b(f-?1|j-?1|visa|i-?20|opt|cpt|sevis|dso|issc|immigration)\b", re.I)
MEETING_RE = re.compile(r"\b(meet(?:ing)?|1:1|one[- ]on[- ]one|talk)\b.*\b(supervisor|manager|boss)\b", re.I)
HOURS_RE = re.compile(r"\b(more hours|extra (?:hours|shifts?)|need (?:more )?hours|pick up (?:a |more |extra )?shifts?)\b",
                      re.I)
CATEGORIES = [("safety", r"unsafe|harass|threat|injur|hurt|fire|danger|exit"),
              ("facilities", r"leak|spill|bathroom|restroom|clean|air condition|\bheat|\blights?\b"),
              ("equipment", r"printer|computer|scanner|laptop|register|card reader|phone|desk|chair|key|door|badge|"
                            r"toner|paper"),
              ("schedule", r"schedule|hours|shift|timesheet|workday")]


def intent(text: str) -> str | None:
    """Work-life requests that aren't calendar items: a visa question (for ISSC), an issue report, a meeting, or
    wanting more hours."""
    if VISA_RE.search(text) and ("?" in text or ASKS_RE.search(text)):
        return "visa"
    if ISSUE_RE.search(text):
        return "issue"
    if MEETING_RE.search(text):
        return "meeting"
    if HOURS_RE.search(text):
        return "hours"
    return None


def issue_category(text: str) -> str:
    return next((name for name, pat in CATEGORIES if re.search(pat, text, re.I)), "other")


def callout(text: str, monday: date, today: date | None = None) -> dict | None:
    """A same-day call-out ("I'm sick, tag me out of Thursday"), or None. No LLM: the words are few and fixed.

    Returns the weekday (0=Mon) and hour the student named, when they named one."""
    if not any(not NEGATED_RE.search(text[:m.start()]) for m in CALLOUT_RE.finditer(text)):
        return None
    day = None
    rel = RELATIVE_RE.search(text)
    if rel and today is not None:
        d = today + timedelta(days=1 if rel.group(1).lower() == "tomorrow" else 0)
        if monday <= d < monday + timedelta(days=7):
            day = d.weekday()
    elif (m := DAY_RE.search(text)) is not None:
        day = _day_index(m.group(1))
    t = TIME_RE.search(text) or RANGE_RE.search(text)
    hour = _hour(t.group(1), t.group(2), t.group(3))[0] if t else None
    return {"weekday": day, "hour": hour}


def _hour(h: str, m: str | None, ap: str | None, default_pm: bool = True) -> tuple[int, int]:
    hh, mm = int(h), int(m or 0)
    if ap:
        if ap.lower() == "pm" and hh < 12:
            hh += 12
        if ap.lower() == "am" and hh == 12:
            hh = 0
    elif default_pm and 1 <= hh <= 7:
        hh += 12  # "career fair 1-4" means afternoon
    return hh, mm


def _day_index(word: str) -> int:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(word[:3].lower())


def parse_regex(text: str, monday: date) -> dict:
    """Deterministic fallback with the same output shape as the Claude tool."""
    events, prefs = [], {"wants_more_hours": None, "never_weekdays": []}
    never = NEVER_RE.search(text)
    if never:
        prefs["never_weekdays"] = [_day_index(never.group(2))]
    if re.search(r"\b(more hours|extra shifts?|need hours)\b", text, re.I):
        prefs["wants_more_hours"] = True
    day = DAY_RE.search(text)
    if day and not never:
        d = monday + timedelta(days=_day_index(day.group(1)))
        rng, one = RANGE_RE.search(text), TIME_RE.search(text)
        if rng:
            ap_end = rng.group(6)
            start = _hour(rng.group(1), rng.group(2), rng.group(3) or ap_end)
            end = _hour(rng.group(4), rng.group(5), ap_end)
        elif one:
            start = _hour(one.group(1), one.group(2), one.group(3))
            kind = classify(text)
            dur = 3 if "fair" in text.lower() else 1
            end = (start[0] + dur, start[1]) if kind != "other" else (start[0] + 1, start[1])
        else:
            start, end = (9, 0), (17, 0)
        title = re.sub(r"\s+", " ", DAY_RE.sub("", RANGE_RE.sub("", TIME_RE.sub("", text)))).strip(" ,.!-")
        title = re.sub(r"^(i got|i have|got|have)\s+(the|a|an)?\s*", "", title, flags=re.I)[:60] or "busy"
        events.append({"title": title, "kind": classify(text), "date": d.isoformat(),
                       "start": f"{start[0]:02d}:{start[1]:02d}", "end": f"{min(end[0], 23):02d}:{end[1]:02d}"})
    return {"events": events, "preferences": prefs}


ROUTE_TOOL = {
    "name": "route_text",
    "description": "Say what a student's text to their own scheduling assistant asks for.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {"type": "string", "enum": ["callout", "visa_question", "issue_report", "meeting_request",
                                                  "more_hours", "calendar"],
                       "description": "callout: they can't work a shift they're scheduled for (sick, emergency, "
                                      "can't come in); visa_question: a question about F-1/J-1, OPT, CPT or work "
                                      "authorization; issue_report: a problem at work (broken equipment, a mess, "
                                      "something unsafe); meeting_request: they want a meeting with their "
                                      "supervisor; more_hours: they want extra shifts; calendar: anything else "
                                      "(events, appointments, preferences)."},
            "weekday": {"type": ["integer", "null"], "minimum": 0, "maximum": 6,
                        "description": "for a callout: the day they named (0=Monday), else null"},
            "hour": {"type": ["integer", "null"], "minimum": 0, "maximum": 23,
                     "description": "for a callout: the hour they named, 24h, else null"},
            "category": {"type": ["string", "null"], "enum": ["equipment", "facilities", "safety", "schedule", "other",
                                                              None],
                         "description": "for an issue report, else null"},
        },
        "required": ["intent", "weekday", "hour", "category"],
    },
}
ROUTE_SYSTEM = ("You route short texts a student worker sends to their own scheduling assistant. Pick the one intent "
                "that fits best. Resolve 'today' and 'tomorrow' against the date given. You only route; the "
                "assistant's own code checks every work rule.")
ROUTES = {"callout": "callout", "visa_question": "visa", "issue_report": "issue", "meeting_request": "meeting",
          "more_hours": "hours", "calendar": "calendar"}


def route(text: str, monday: date, today: date | None = None) -> tuple[dict, str]:
    """What a text asks for: callout, visa, issue, meeting, hours or calendar, plus the day and hour of a call-out.
    Claude Haiku routes it when online (cached, under the spend cap); the regex rules above route it otherwise."""
    if not llm.offline():
        user = (f"Today is {(today or monday):%A %Y-%m-%d}. The work week starts Monday {monday.isoformat()}.\n"
                f"Text: {text}")
        out = llm.call_tool(llm.PARSE_MODEL, ROUTE_SYSTEM, user, ROUTE_TOOL, max_tokens=200)
        if out and out.get("intent") in ROUTES:
            r = {"intent": ROUTES[out["intent"]], "weekday": out.get("weekday"), "hour": out.get("hour"),
                 "category": out.get("category")}
            if r["intent"] == "callout" and r["weekday"] is None:  # the words may still name a day
                r.update({k: v for k, v in (callout(text, monday, today) or {}).items() if v is not None})
            if r["intent"] == "issue" and not r["category"]:
                r["category"] = issue_category(text)
            return r, "claude"
    c = callout(text, monday, today)
    if c is not None:
        return {"intent": "callout", **c, "category": None}, "regex"
    k = intent(text)
    return {"intent": k or "calendar", "weekday": None, "hour": None,
            "category": issue_category(text) if k == "issue" else None}, "regex"


def parse(text: str, monday: date, seed: bool = False) -> tuple[dict, str]:
    """Return (parsed, engine). Engine is 'claude' or 'regex'."""
    user = (f"Reference week: Monday {monday.isoformat()} to Sunday {(monday + timedelta(days=6)).isoformat()}. "
            f"Days: " + ", ".join(f"{DAY_NAMES[i]}={(monday + timedelta(days=i)).isoformat()}" for i in range(7))
            + f"\nText: {text}")
    out = llm.call_tool(llm.PARSE_MODEL, SYSTEM, user, TOOL, seed=seed)
    if out is not None and isinstance(out.get("events"), list):
        return out, "claude"
    return parse_regex(text, monday), "regex"


def to_blocks(parsed: dict, source: str = "text") -> list[BusyBlock]:
    out = []
    for e in parsed.get("events", []):
        try:
            d = date.fromisoformat(e["date"])
            s = datetime.combine(d, time.fromisoformat(e["start"]), tzinfo=PHX)
            en = datetime.combine(d, time.fromisoformat(e["end"]), tzinfo=PHX)
        except (KeyError, ValueError):
            continue
        if en <= s:
            en = s + timedelta(hours=1)
        kind = e.get("kind") if e.get("kind") in KINDS else classify(e.get("title", ""))
        out.append(BusyBlock(id=_bid(source, e.get("title", "busy"), s), start=s, end=en, kind=kind,
                             label=e.get("title", "busy")[:80], source=source))  # type: ignore[arg-type]
    return out
