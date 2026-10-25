"""Record the real system for the hosted replay (site/data/*.json): every agent ran, nothing is scripted by hand.

    python -m scripts.record          # writes site/data/tour.json, breakit.json and org.json

Each recording holds the public event stream, every phone message with its time, and snapshots of what each page
asks the broker for, taken after each step. The hosted site replays them; `python -m scripts.run_all` runs it live.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

# recordings parse texts with the regex fallback or the committed cache, never the API; the hosted /api/try may
# turn the API on for a visitor's own text (site/api/try.py)
os.environ.setdefault("TAGOUT_OFFLINE", "1")

from broker.engine import Timing  # noqa: E402
from scripts.inproc import System  # noqa: E402
from seeds.org import ORG_DEMO, ORG_STUDENTS  # noqa: E402
from seeds.scenario import STUDENTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
PEOPLE = [s["id"] for s in STUDENTS]
PACE = Timing(pick_deadline=0.4, ask_window=1.5, vote_timeout=15.0, between=0.5)
ORG_MINUTE = 0.045  # real seconds per story minute for the hierarchy: its two-hour timer plays in 5.4 s


async def snapshot(s: System) -> dict:
    paths = ["/state", "/agents", "/manager/state", "/admin/judge", "/admin/baseline", "/forecast", "/sim", "/quotes",
             "/org", "/me/raj"]
    paths += [f"/me/{p}" for p in PEOPLE]
    out = {}
    for path in paths:
        try:
            r = await s.net.client.get(f"{s.reg['broker']}{path}")
            if r.status_code == 200:
                out[path] = r.json()
        except Exception:
            pass
    return out


async def until(cond, timeout: float = 40.0) -> None:
    async def poll():
        while not cond():
            await asyncio.sleep(0.05)
    await asyncio.wait_for(poll(), timeout)


def summary_after(s: System, n: int, kind: str):
    return lambda: any(e["type"] == "summary" and e.get("kind") == kind for e in s.bus.history[n:])


async def record(name: str, steps) -> None:
    s = System(timing=PACE, auto_delay=0.8, tmp=Path(tempfile.mkdtemp(prefix=f"tagout-{name}-")),
               org_minute=ORG_MINUTE)
    checkpoints = [{"label": "start", "n": 0, "snap": await snapshot(s)}]
    try:
        for label, step in steps:
            await step(s)
            await asyncio.sleep(1.0)
            checkpoints.append({"label": label, "n": len(s.bus.history), "snap": await snapshot(s)})
            print(f"  {name}: {label} ({len(s.bus.history)} events)")
        phones = {p: s.store(p).outbox() for p in PEOPLE + [o["id"] for o in ORG_STUDENTS]}
        phones["manager"] = [{"n": i + 1, **m} for i, m in enumerate(s.steward.state.s["phone"])]
        phones |= {r: [{"n": i + 1, **m} for i, m in enumerate(a.state.s["phone"])] for r, a in s.org.items()}
        data = {"name": name, "events": s.bus.history, "phones": phones, "checkpoints": checkpoints}
        OUT.mkdir(parents=True, exist_ok=True)
        if name == "tour":  # the roster downloads the hosted page links to, as the manager would get them
            for f in ("roster.csv", "roster.ics"):
                r = await s.net.client.get(f"{s.reg['broker']}/{f}")
                (OUT / f).write_bytes(r.content)
        (OUT / f"{name}.json").write_text(json.dumps(data, default=str), encoding="utf-8")
        print(f"saved {OUT / (name + '.json')} ({len(s.bus.history)} events)")
    finally:
        await s.close()


async def intake(s: System, who: str, text: str) -> None:
    await s.net.post(f"{s.reg['agents'][who]}/intake", {"text": text})


def manager_said(s: System, words: str):
    return lambda: any(words in m["text"] for m in s.steward.state.s["phone"])


async def sunday(s: System) -> None:
    await s.post("/demo/sunday")
    await asyncio.sleep(2.5)  # students tap "Find a trade"


async def week(s: System) -> None:
    n = len(s.bus.history)
    await s.post("/demo/run")
    await until(summary_after(s, n, "week"), 90)


async def callout(s: System) -> None:
    n = len(s.bus.history)
    await intake(s, "ben", "I woke up sick, can't make it Monday")
    await until(summary_after(s, n, "callout"))


async def extra(s: System) -> None:
    n = len(s.bus.history)
    await s.post("/manager/extra", {"date": "2026-10-29", "start": 18, "end": 22})
    await until(summary_after(s, n, "extra"))


async def issue(s: System) -> None:
    await intake(s, "ana", "the printer at the desk is broken again")
    await until(lambda: any("Your manager saw your report" in m["text"] for m in s.phone("ana")))


async def team_meeting(s: System) -> None:
    await s.post("/manager/meeting", {})
    await until(manager_said(s, "coming"))


async def supervisor_meeting(s: System) -> None:
    await intake(s, "priya", "can I set up a meeting with my supervisor?")
    await until(manager_said(s, "booked a 30-minute meeting"))


async def snoop(s: System) -> None:
    await s.post("/demo/snoop")


# ----- the campus hierarchy (org/app.py), recorded on its own: org.json -----
def org_done_after(s: System, n: int):
    return lambda: any(e["type"] in ("org_done", "org_pending") for e in s.bus.history[n:])


async def org_text(s: System, who: str, text: str) -> None:
    n = len(s.bus.history)
    await s.net.post(f"{s.reg['org'][who]}/intake", {"text": text})
    await until(org_done_after(s, n), 60)


async def org_callout(s: System) -> None:
    await org_text(s, *ORG_DEMO["callout"])


async def org_safety(s: System) -> None:
    await org_text(s, *ORG_DEMO["safety"])


async def org_question(s: System) -> None:
    await org_text(s, *ORG_DEMO["question"])


async def break_it(s: System) -> None:
    await s.post("/admin/auto", {"enabled": False, "agents": ["dev"], "delay": 0.8})
    await s.post("/demo/sunday")
    await asyncio.sleep(2.5)
    await s.net.post(f"{s.reg['agents']['dev']}/tap", {"data": "trade:yes:library-fri-1030-1000-d1"})
    n = len(s.bus.history)
    await s.post("/demo/run")
    await until(lambda: any(e["type"] == "prepare" for e in s.bus.history[n:]))
    await asyncio.sleep(1.5)
    await s.post("/demo/break")
    await until(lambda: any(e["type"] == "abort" for e in s.bus.history[n:]))
    await s.post("/admin/auto", {"enabled": True, "agents": ["dev"], "delay": 0.8})
    await until(summary_after(s, n, "week"), 120)


FAST = Timing(pick_deadline=0.05, ask_window=0.3, vote_timeout=8.0, between=0.05)
ORG_IDS = [o["id"] for o in ORG_STUDENTS]  # Dining and Rec center students: their texts go up the hierarchy
TRY_ORG_MINUTE = 0.02  # the hosted run: a two-hour timer plays in 2.4 s, so a whole climb fits the function's minute


async def try_message(who: str, text: str, tmp: Path | None = None) -> dict:
    """The hosted page's own-message path: run the real system through the week, then send one student's mascot
    the visitor's text and record what every agent did with it. A Dining or Rec student's text skips the Library
    week and runs the campus hierarchy instead: any case it opens climbs until someone closes it."""
    org = who in ORG_IDS
    s = System(timing=FAST, auto_delay=0.05, tmp=tmp or Path(tempfile.mkdtemp(prefix="tagout-try-")),
               **({"org_minute": TRY_ORG_MINUTE} if org else {}))
    try:
        checkpoints = [{"label": "start", "n": 0, "snap": await snapshot(s)}]
        if not org:
            await s.post("/demo/sunday")
            await asyncio.sleep(0.4)
            await week(s)
        checkpoints.append({"label": "week", "n": len(s.bus.history), "snap": await snapshot(s)})
        n, before = len(s.bus.history), len(s.phone(who))
        r = await s.net.post(f"{(s.reg['org'] if org else s.reg['agents'])[who]}/intake", {"text": text})
        kind = r.get("engine")
        try:
            if org:
                await asyncio.sleep(1.0)
                if any(e["type"] == "org_case" for e in s.bus.history[n:]):
                    await until(lambda: any(e["type"] in ("org_done", "org_pending", "org_overdue")
                                            for e in s.bus.history[n:]), 40)
            elif kind == "callout" and "Which shift" not in r.get("reply", ""):
                await until(summary_after(s, n, "callout"), 20)
            elif kind == "issue":
                await until(lambda: any("Your manager saw your report" in m["text"] for m in s.phone(who)), 10)
            elif kind == "meeting":
                await until(manager_said(s, "booked a"), 10)
            elif kind == "visa":
                await until(org_done_after(s, n), 10)
            else:
                await asyncio.sleep(0.5)
        except TimeoutError:
            pass
        await asyncio.sleep(0.3)
        checkpoints.append({"label": "try", "n": len(s.bus.history), "snap": await snapshot(s)})
        phones = {p: s.store(p).outbox() for p in PEOPLE + ORG_IDS}
        phones["manager"] = [{"n": i + 1, **m} for i, m in enumerate(s.steward.state.s["phone"])]
        phones |= {r: [{"n": i + 1, **m} for i, m in enumerate(a.state.s["phone"])] for r, a in s.org.items()}
        return {"name": "try", "who": who, "engine": kind, "new_messages": len(s.phone(who)) - before,
                "events": s.bus.history, "phones": phones, "checkpoints": checkpoints}
    finally:
        await s.close()


async def main() -> None:
    os.environ["TAGOUT_OFFLINE"] = "1"
    await record("tour", [("sunday", sunday), ("week", week), ("callout", callout), ("extra", extra),
                          ("issue", issue), ("team-meeting", team_meeting), ("supervisor-meeting", supervisor_meeting),
                          ("snoop", snoop)])
    await record("breakit", [("break-it", break_it)])
    # the hierarchy's morning comes after the Library's week, so its replay starts from the finished week
    await record("org", [("sunday", sunday), ("week", week), ("callout", org_callout), ("safety", org_safety),
                         ("question", org_question)])


if __name__ == "__main__":
    asyncio.run(main())
