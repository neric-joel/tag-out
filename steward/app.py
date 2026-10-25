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
from core.timeutil import PHX, fmt_span, planning_monday
from core.wire import BusyBits, CallOut, Decision, Move, OpenShift, Prepare, ShiftRef, SlotQuery, Vote
from ingest.ics import read, shifts_from_ics
from seeds.scenario import EMPLOYER, STUDENTS

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"
K_ANON = 3  # the forecast only reports a slot when at least this many people are affected


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
    names = {s["id"]: s["name"] for s in STUDENTS}
    state = {"roster": load_roster(), "version": 1, "holds": {}, "ballots": {}, "changed": {}, "phone": [],
             "auto": os.environ.get("TAGOUT_MODE", "auto") == "auto",
             "delay": float(os.environ.get("TAGOUT_AUTO_DELAY", "1.5")) + 0.5, "open": [],
             "swap_rule": swap_rule_default()}
    app.state.s = state

    async def to_manager(text: str, buttons: list[tuple[str, str]], kind: str = "approve") -> None:
        msg = {"kind": kind, "text": text, "buttons": [{"label": a, "data": b} for a, b in buttons]}
        state["phone"].append(msg)
        try:
            await app.state.net.post(f"{reg['bot']}/send", {"student_id": "manager", **msg})
        except Exception:
            pass
        if state["auto"] and buttons and kind == "approve":
            async def later() -> None:
                await asyncio.sleep(state["delay"])
                await handle_tap(buttons[0][1])
            asyncio.create_task(later())

    async def handle_tap(data: str) -> str:
        if data.startswith("rule:swaps:"):
            state["swap_rule"] = data.endswith(":on")
            reply = ("OK: swaps that keep every shift covered go through without you again." if state["swap_rule"]
                     else "OK: I'll ask you about every trade, swaps included.")
            state["phone"].append({"kind": "reply", "text": reply, "buttons": []})
            return reply
        verb, _, txn = data.partition(":")
        if txn not in state["holds"]:
            return "That request is closed."
        vote = "yes" if verb == "approve" else "no"
        await app.state.net.post(f"{reg['broker']}/txn/vote", Vote(txn_id=txn, agent_id="steward", vote=vote,
                                                                    ballot=state["ballots"].get(txn, "")))
        state["phone"].append({"kind": "reply", "text": "Approved." if vote == "yes" else "Denied.", "buttons": []})
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
        lines = [f"{names[m.from_agent]}'s {fmt_span(state['roster'][m.shift_id].start, state['roster'][m.shift_id].end)}"
                 f" -> {names[m.to_agent]}" for m in p.moves]
        if state["swap_rule"] and is_swap(p.moves):
            # the manager's standing rule: a swap changes who works, not coverage or anyone's hours
            await to_manager("Approved under your standing rule for swaps: " + "; ".join(lines) + ". Every shift "
                             "stays covered and nobody's hours change. It still needs every student to confirm.",
                             [("Ask me each time", "rule:swaps:off")], kind="info")
            return {"vote": Vote(txn_id=p.txn_id, agent_id="steward", vote="yes", ballot=p.ballot).model_dump()}
        text = ("Trade request: " + "; ".join(lines) + ". Each student's mascot privately checked the trade "
                "against the shifts and other jobs it knows about for its student and said eligible; no reasons are "
                "shared. It goes through only if every student confirms and you approve. If you don't answer in "
                "time, nothing moves and everyone keeps the shift they were scheduled for.")
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
                done.append(f"{names[m.to_agent]} now works {fmt_span(ref.start, ref.end)}")
            state["version"] += 1
            state["phone"].append({"kind": "info", "buttons": [], "text": "Roster updated: " + "; ".join(done)
                                   + ". Download it for your scheduler (CSV or calendar file) from the Library "
                                     "roster on the Tag Out page. Students enter their time in Workday as usual."})
        return {}

    def export_rows() -> list[dict]:
        rows = []
        for r in sorted(state["roster"].values(), key=lambda x: x.start):
            rows.append({"date": f"{r.start:%Y-%m-%d}", "start": f"{r.start:%H:%M}", "end": f"{r.end:%H:%M}",
                         "position": "Library front desk", "worker": names.get(r.owner, r.owner),
                         "changed_by_trade": "yes" if r.shift_id in state["changed"] else "",
                         "shift_id": r.shift_id})
        return rows

    @app.get("/export.csv")
    async def export_csv() -> Response:
        """The approved roster for the manager's own scheduler or shared sheet (When I Work, Sling, Excel)."""
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=["date", "start", "end", "position", "worker", "changed_by_trade",
                                            "shift_id"])
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
                     swap_rule=swap_rule_default())
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
