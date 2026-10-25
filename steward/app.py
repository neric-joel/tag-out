"""The Steward: the employer's agent. It owns the roster, approves trades through the real manager, and gives a
crunch forecast with counts only. Run: uvicorn steward.app:app --port 8701
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
from datetime import datetime, timedelta
from pathlib import Path

import icalendar
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from core.net import Net, registry
from core.timeutil import PHX, fmt_span, overlaps, planning_monday
from core.wire import (
    BusyBits,
    CallOut,
    Decision,
    IssueAck,
    IssueReport,
    MeetingBook,
    MeetingInvite,
    MeetingOptions,
    MeetingRequest,
    Move,
    OpenShift,
    Prepare,
    Rsvp,
    ShiftRef,
    SlotQuery,
    Vote,
)
from ingest.ics import read, shifts_from_ics
from seeds.scenario import EMPLOYER, MANAGER, STUDENTS

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"
K_ANON = 3  # the forecast only reports a slot when at least this many people are affected
CHECKS = ("class time, the 40-hour week, any weekly cap on hours across all jobs (as each student reported their other "
          "jobs), the 25-hour average and any award limit")


class Tap(BaseModel):
    data: str


def load_roster() -> dict[str, ShiftRef]:
    roster: dict[str, ShiftRef] = {}
    monday = planning_monday()
    start, end = monday - timedelta(days=7), monday + timedelta(days=14)
    for s in STUDENTS:
        for sh in shifts_from_ics(read(ICS / f"{s['id']}_library.ics"), EMPLOYER, start, end):
            roster[sh.id] = ShiftRef(shift_id=sh.id, employer=EMPLOYER, start=sh.start, end=sh.end, owner=s["id"])
    return roster


def swap_rule_default() -> bool:
    """The manager's standing rule: swaps (same hours each way, every shift still covered) need no approval."""
    return os.environ.get("TAGOUT_SWAP_RULE", "on") != "off"


def create_app(net: Net | None = None, reg: dict | None = None) -> FastAPI:
    app = FastAPI(title="Tag Out steward (Library)")
    reg = reg or registry()
    app.state.net = net or Net()
    if net is None and os.environ.get("TAGOUT_DEBUG") == "1":
        app.state.net.report_to(reg["broker"])  # the judge view's agent graph
    names = {s["id"]: s["name"] for s in STUDENTS}
    state = {"roster": load_roster(), "version": 1, "holds": {}, "ballots": {}, "changed": {}, "phone": [],
             "auto": os.environ.get("TAGOUT_MODE", "auto") == "auto",
             "delay": float(os.environ.get("TAGOUT_AUTO_DELAY", "1.5")) + 0.5, "open": [],
             "swap_rule": swap_rule_default(), "issues": {}, "meetings": {}, "extras": [], "checked": {}}
    app.state.s = state

    def phone_add(msg: dict) -> None:
        state["phone"].append({"ts": datetime.now(PHX).isoformat(timespec="seconds"), **msg})

    async def to_manager(text: str, buttons: list[tuple[str, str]], kind: str = "approve") -> None:
        msg = {"kind": kind, "text": text, "buttons": [{"label": a, "data": b} for a, b in buttons]}
        phone_add(msg)
        try:
            await app.state.net.post(f"{reg['bot']}/send", {"student_id": "manager", **msg})
        except Exception:
            pass
        if state["auto"] and buttons and kind in ("approve", "issue", "choose"):
            async def later() -> None:
                await asyncio.sleep(state["delay"])
                await handle_tap(buttons[0][1])
            asyncio.create_task(later())

    async def handle_tap(data: str) -> str:
        if data.startswith("ack:"):
            it = state["issues"].get(data[4:])
            if not it or it["status"] != "new":
                return "Already handled."
            it["status"] = "acknowledged"
            if it["agent_id"]:
                await app.state.net.post(f"{reg['agents'][it['agent_id']]}/issue/ack", IssueAck(issue_id=data[4:]))
            reply = "Acknowledged." + (f" {names[it['agent_id']]}'s mascot will let them know." if it["agent_id"] else "")
            phone_add({"kind": "reply", "text": reply, "buttons": []})
            return reply
        if data.startswith("meet:"):
            _, mid, i = data.split(":")
            m = state["meetings"].get(mid)
            if not m or m["chosen"] is not None:
                return "That meeting is already set."
            m["chosen"] = int(i)
            s, e = (datetime.fromisoformat(x) for x in m["options"][int(i)]["slot"])
            inv = MeetingInvite(meeting_id=mid, start=s, end=e, title="Library team meeting")
            await asyncio.gather(*(app.state.net.post(f"{u}/meeting/invite", inv) for u in reg["agents"].values()),
                                 return_exceptions=True)
            reply = (f"Invites sent to {len(reg['agents'])} students for {fmt_span(s, e)}. I'll tell you who can "
                     "come, never why.")
            phone_add({"kind": "reply", "text": reply, "buttons": []})
            return reply
        if data.startswith("rule:swaps:"):
            state["swap_rule"] = data.endswith(":on")
            reply = ("OK: swaps that keep every shift covered go through without you again." if state["swap_rule"]
                     else "OK: I'll ask you about every trade, swaps included.")
            phone_add({"kind": "reply", "text": reply, "buttons": []})
            return reply
        verb, _, txn = data.partition(":")
        if txn not in state["holds"]:
            return "That request is closed."
        vote = "yes" if verb == "approve" else "no"
        await app.state.net.post(f"{reg['broker']}/txn/vote", Vote(txn_id=txn, agent_id="steward", vote=vote,
                                                                    ballot=state["ballots"].get(txn, "")))
        phone_add({"kind": "reply", "text": "Approved." if vote == "yes" else "Denied.", "buttons": []})
        return "Approved." if vote == "yes" else "Denied."

    @app.get("/roster", response_model=list[ShiftRef])
    async def roster() -> list[ShiftRef]:
        return sorted(state["roster"].values(), key=lambda r: r.start)

    @app.get("/people")
    async def people() -> dict:
        return names

    @app.get("/version")
    async def version() -> dict:
        return {"agent_id": "steward", "version": state["version"]}

    @app.post("/txn/prepare")
    async def prepare(p: Prepare) -> dict:
        # Freshness on the employer side is per shift: each move's giver must still own that shift.
        for m in p.moves:
            ref = state["roster"].get(m.shift_id)
            if ref is None or ref.owner != m.from_agent:
                return {"vote": Vote(txn_id=p.txn_id, agent_id="steward", vote="stale",
                                     ballot=p.ballot).model_dump()}
        state["holds"][p.txn_id] = [m.model_dump() for m in p.moves]
        state["ballots"][p.txn_id] = p.ballot
        lines = [f"{names.get(m.from_agent, 'Open')}'s {fmt_span(state['roster'][m.shift_id].start, state['roster'][m.shift_id].end)}"
                 f" -> {names[m.to_agent]}" for m in p.moves]
        if all(m.from_agent == "open" for m in p.moves):
            # an extra shift the manager posted: posting it was the approval
            await to_manager("Extra shift: " + "; ".join(f"{names[m.to_agent]} will take "
                                                          f"{fmt_span(state['roster'][m.shift_id].start, state['roster'][m.shift_id].end)}"
                                                          for m in p.moves)
                             + ". Their mascot checked their classes and work-hour limits in private. It goes through "
                               "when they confirm.", [], kind="info")
            return {"vote": Vote(txn_id=p.txn_id, agent_id="steward", vote="yes", ballot=p.ballot).model_dump()}
        if state["swap_rule"] and is_swap(p.moves):
            # the manager's standing rule: a swap changes who works, not coverage or anyone's hours
            await to_manager("Approved under your standing rule for swaps: " + "; ".join(lines) + ". Every shift "
                             "stays covered and nobody's hours change. It still needs every student to confirm.",
                             [("Ask me each time", "rule:swaps:off")], kind="info")
            return {"vote": Vote(txn_id=p.txn_id, agent_id="steward", vote="yes", ballot=p.ballot).model_dump()}
        text = ("Trade request: " + "; ".join(lines) + ".\nChecked " + datetime.now(PHX).strftime("%a %b %d, %I:%M %p")
                + ": each student's mascot re-checked this exact trade against " + CHECKS + ", and said eligible. "
                "No reasons are shared.\nIt goes through only if every student confirms and you approve. If you "
                "don't answer in time, nothing moves and everyone keeps the shift they were scheduled for.")
        await to_manager(text, [("Approve", f"approve:{p.txn_id}"), ("Deny", f"deny:{p.txn_id}")])
        return {"vote": None}

    def is_swap(moves: list[Move]) -> bool:
        """Every member gives and takes the same hours, so coverage and everyone's hours are unchanged."""
        net: dict[str, float] = {}
        for m in moves:
            ref = state["roster"][m.shift_id]
            h = (ref.end - ref.start).total_seconds() / 3600
            net[m.from_agent] = net.get(m.from_agent, 0.0) - h
            net[m.to_agent] = net.get(m.to_agent, 0.0) + h
        return all(abs(v) < 1e-9 for v in net.values())

    def when(ref: ShiftRef) -> str:
        left = (ref.start - datetime.now(PHX)).total_seconds() / 3600
        day = f"{fmt_span(ref.start, ref.end)} ({ref.start:%b} {ref.start.day})"
        return f"{day}, starting in {left:.0f} h" if 0 < left < 24 else day

    # ----- the manager's screen: post an extra shift, find a team meeting time, see what's open -----
    @app.post("/manager/extra")
    async def post_extra(body: dict) -> dict:
        day = datetime.fromisoformat(str(body["date"])).date()
        start, end = int(body.get("start", 18)), int(body.get("end", 22))
        st = datetime(day.year, day.month, day.day, start, tzinfo=PHX)
        ref = ShiftRef(shift_id=f"library-extra-{st:%m%d-%H%M}", employer=EMPLOYER, start=st,
                       end=st + timedelta(hours=end - start), owner="open")
        state["roster"][ref.shift_id] = ref
        state["extras"].append(ref.shift_id)
        phone_add({"kind": "info", "buttons": [], "text": f"Posted an extra shift: {fmt_span(ref.start, ref.end)}. "
                               "Every student's mascot gets offered it; only those who want hours and fit every limit "
                               "will pick it, and you won't see why anyone passed."})
        await app.state.net.post(f"{reg['broker']}/extra", ref)
        return {"shift_id": ref.shift_id}

    def manager_busy(st: datetime, en: datetime) -> bool:
        return any(st.weekday() == d and overlaps(st, en, st.replace(hour=a, minute=0), st.replace(hour=b, minute=0))
                   for d, a, b in MANAGER["busy"])

    @app.post("/manager/meeting")
    async def team_meeting(body: dict) -> dict:
        """Find the hour next week when most of the team is free. Each mascot answers busy or free per slot;
        no calendar leaves a mascot."""
        mon = planning_monday()
        slots = {}
        for d in range(5):
            day = mon + timedelta(days=d)
            for h in range(9, 17):
                st = datetime(day.year, day.month, day.day, h, tzinfo=PHX)
                if not manager_busy(st, st + timedelta(hours=1)):
                    slots[f"{st:%a %H}"] = (st, st + timedelta(hours=1))
        free = dict.fromkeys(slots, 0)
        replies = await asyncio.gather(*(app.state.net.post(f"{u}/busybits", SlotQuery(slots=slots))
                                         for u in reg["agents"].values()), return_exceptions=True)
        for r in replies:
            if isinstance(r, dict):
                for k, busy in BusyBits(**r).slots.items():
                    free[k] += int(not busy)
        best = sorted(slots, key=lambda k: (-free[k], slots[k][0]))[:3]
        mid = f"team-{len(state['meetings']) + 1}"
        options = [{"slot": [slots[k][0].isoformat(), slots[k][1].isoformat()], "free": free[k]} for k in best]
        state["meetings"][mid] = {"options": options, "chosen": None, "rsvp": {}}
        staff = len(reg["agents"])
        text = ("Team meeting: the best hours next week, by how many of your " + str(staff) + " students are free. "
                "Each mascot only answered busy or free per hour, never what's on the calendar. Pick one and I'll "
                "invite everyone.")
        await to_manager(text, [(f"{fmt_span(slots[k][0], slots[k][1])} · {free[k]} free", f"meet:{mid}:{i}")
                                for i, k in enumerate(best)], kind="choose")
        return {"meeting_id": mid, "options": options}

    @app.post("/meeting/rsvp")
    async def meeting_rsvp(r: Rsvp) -> dict:
        m = state["meetings"].get(r.meeting_id)
        if m is not None:
            m["rsvp"][r.agent_id] = r.going
            if len(m["rsvp"]) == len(reg["agents"]):
                going = sum(m["rsvp"].values())
                s, e = m["options"][m["chosen"]]["slot"]
                phone_add({"kind": "info", "buttons": [], "text": f"Team meeting {fmt_span(datetime.fromisoformat(s), datetime.fromisoformat(e))}: "
                                       f"{going} coming, {len(m['rsvp']) - going} can't make it (no reasons)."})
        return {}

    @app.post("/meeting/request", response_model=MeetingOptions)
    async def meeting_request(req: MeetingRequest) -> MeetingOptions:
        """A student's mascot sent the times its student is free; offer up to three the manager is free too,
        on different days."""
        out, days = [], set()
        for s, e in req.slots:
            if not manager_busy(s, e) and s.date() not in days:
                out.append((s, e))
                days.add(s.date())
            if len(out) == 3:
                break
        return MeetingOptions(request_id=req.request_id, slots=out)

    @app.post("/meeting/book")
    async def meeting_book(b: MeetingBook) -> dict:
        phone_add({"kind": "info", "buttons": [], "text": f"{names[b.agent_id]} booked a "
                               f"{int((b.end - b.start).total_seconds() // 60)}-minute meeting with you: "
                               f"{fmt_span(b.start, b.end)} ({b.start:%b} {b.start.day}). Topic not shared."})
        return {}

    @app.post("/issue")
    async def issue(r: IssueReport) -> dict:
        state["issues"][r.issue_id] = {"category": r.category, "text": r.text, "agent_id": r.agent_id,
                                       "status": "new"}
        who = names[r.agent_id] if r.agent_id else "anonymous"
        hr = reg.get("org", {}).get("hr")
        if r.category == "safety" and hr:  # safety skips the ladder: Student Employment gets it at once too
            asyncio.create_task(app.state.net.post(f"{hr}/issue", r))
        await to_manager(f"Issue reported ({r.category}): \"{r.text}\"\nFrom: {who}."
                         + ("\nSafety reports also go straight to Student Employment." if r.category == "safety" and hr
                            else ""), [("Acknowledge", f"ack:{r.issue_id}")], kind="issue")
        return {}

    @app.get("/manager/state")
    async def manager_state() -> dict:
        roster = sorted(state["roster"].values(), key=lambda x: x.start)
        return {"swap_rule": state["swap_rule"], "open": state["open"], "extras": state["extras"],
                "issues": [{"id": k, **v, "from": names.get(v["agent_id"], "anonymous") if v["agent_id"] else "anonymous"}
                           for k, v in state["issues"].items()],
                "meetings": state["meetings"],
                "pending": [{"txn_id": t, "moves": m} for t, m in state["holds"].items()],
                "roster": [r.model_dump(mode="json") for r in roster]}

    @app.post("/callout")
    async def callout(body: CallOut) -> dict:
        """A same-day call-out: the manager hears at once, before any round finishes. No reason attached."""
        ref = state["roster"].get(body.shift_id)
        if ref is not None:
            who = names[ref.owner]
            await to_manager(f"Same-day request: {who} can't work {when(ref)}. A cover round is running now; if a "
                             f"coworker takes it you'll get a card to approve. Until then {who} is still on the "
                             "schedule. No reason given.", [], kind="info")
        return {}

    @app.post("/txn/decide")
    async def decide(d: Decision) -> dict:
        moves = state["holds"].pop(d.txn_id, None)
        if moves and d.outcome == "commit":
            done = []
            for m in map(lambda x: Move(**x), moves):
                ref = state["roster"][m.shift_id]
                state["roster"][m.shift_id] = ref.model_copy(update={"owner": m.to_agent})
                state["changed"][m.shift_id] = d.txn_id
                state["checked"][m.shift_id] = datetime.now(PHX).isoformat(timespec="minutes")
                done.append(f"{names[m.to_agent]} now works {fmt_span(ref.start, ref.end)}")
            state["version"] += 1
            phone_add({"kind": "info", "buttons": [], "text": "Roster updated: " + "; ".join(done)
                                   + ". Download it for your scheduler (CSV or calendar file) from the Library "
                                     "roster on the Tag Out page. Students enter their time in Workday as usual."})
        return {}

    def export_rows() -> list[dict]:
        rows = []
        for r in sorted(state["roster"].values(), key=lambda x: x.start):
            rows.append({"date": f"{r.start:%Y-%m-%d}", "start": f"{r.start:%H:%M}", "end": f"{r.end:%H:%M}",
                         "position": "Library front desk", "worker": names.get(r.owner, r.owner),
                         "changed_by_trade": "yes" if r.shift_id in state["changed"] else "",
                         "checked_at": state["checked"].get(r.shift_id, ""),
                         "checked": CHECKS if r.shift_id in state["changed"] else "",
                         "shift_id": r.shift_id})
        return rows

    @app.get("/export.csv")
    async def export_csv() -> Response:
        """The approved roster for the manager's own scheduler or shared sheet (When I Work, Sling, Excel)."""
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=["date", "start", "end", "position", "worker", "changed_by_trade",
                                            "checked_at", "checked", "shift_id"])
        w.writeheader()
        w.writerows(export_rows())
        return Response(out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=library-roster.csv"})

    @app.get("/export.ics")
    async def export_ics() -> Response:
        cal = icalendar.Calendar()
        cal.add("prodid", "-//Tag Out//Library roster//EN")
        cal.add("version", "2.0")
        for r in sorted(state["roster"].values(), key=lambda x: x.start):
            ev = icalendar.Event()
            ev.add("uid", f"{r.shift_id}@tagout")
            ev.add("summary", f"Library front desk - {names.get(r.owner, r.owner)}")
            ev.add("dtstart", r.start)
            ev.add("dtend", r.end)
            if r.shift_id in state["changed"]:
                ev.add("description", "Changed by an approved Tag Out trade")
            cal.add_component(ev)
        return Response(cal.to_ical(), media_type="text/calendar",
                        headers={"Content-Disposition": "attachment; filename=library-roster.ics"})

    @app.post("/open")
    async def post_open(body: OpenShift) -> dict:
        """A shift no trade could fill: the manager sees it as open, with no reason attached."""
        sid = body.shift_id
        if sid in state["roster"] and sid not in state["open"]:
            state["open"].append(sid)
            ref = state["roster"][sid]
            who = names[ref.owner]
            if body.urgent:
                await to_manager(f"Nobody could take {who}'s same-day {when(ref)} safely. {who} asked to be out, "
                                 "with no reason given. It's your call under your department's call-out policy: "
                                 "excuse them and post the shift, or cover the desk.", [], kind="info")
            else:
                await to_manager(f"No safe trade for {who}'s {fmt_span(ref.start, ref.end)} this week. {who} is "
                                 "still scheduled and asked for a trade, with no reason given. Approve time off and "
                                 "post the shift, or keep them scheduled.", [], kind="info")
        return {}

    @app.post("/tap")
    async def tap(t: Tap) -> dict:
        reply = await handle_tap(t.data)
        return {"reply": reply}

    @app.get("/phone")
    async def phone() -> dict:
        return {"student": "Library manager", "messages": [{"n": i + 1, **m} for i, m in enumerate(state["phone"])]}

    @app.post("/admin/reset")
    async def reset() -> dict:
        if os.environ.get("TAGOUT_DEBUG") != "1":
            raise HTTPException(403)
        state.update(roster=load_roster(), version=1, holds={}, ballots={}, changed={}, phone=[], open=[],
                     swap_rule=swap_rule_default(), issues={}, meetings={}, extras=[], checked={})
        return {"ok": True}

    @app.post("/admin/auto")
    async def auto(body: dict) -> dict:
        state["auto"] = bool(body.get("enabled", True))
        state["delay"] = float(body.get("delay", state["delay"]))
        return {"auto": state["auto"]}

    @app.get("/forecast")
    async def forecast(monday: str | None = None) -> dict:
        """Next week's crunch: for each roster slot, how many staff are busy. Counts only, k >= 3."""
        mon = datetime.fromisoformat(monday).date() if monday else planning_monday()
        slots = {}
        for d in range(7):
            day = mon + timedelta(days=d)
            for a, b in ((10, 14), (14, 18), (18, 22)):
                st = datetime(day.year, day.month, day.day, a, tzinfo=state_tz())
                slots[f"{day:%a} {a}-{b}"] = (st, st + timedelta(hours=b - a))
        counts = dict.fromkeys(slots, 0)
        for url in reg["agents"].values():
            try:
                bits = BusyBits(**await app.state.net.post(f"{url}/busybits", SlotQuery(slots=slots)))
            except Exception:
                continue
            for k, v in bits.slots.items():
                counts[k] += int(v)
        staff = len(reg["agents"])
        alerts = [{"slot": k, "busy": v, "staff": staff} for k, v in counts.items() if v >= K_ANON]
        return {"monday": mon.isoformat(), "staff": staff, "k": K_ANON, "alerts": alerts}

    return app


def state_tz():
    from core.timeutil import PHX
    return PHX


app = create_app() if os.environ.get("TAGOUT_ROLE") == "steward" else None
