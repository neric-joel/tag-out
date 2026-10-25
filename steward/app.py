"""The Steward: the employer's agent. It owns the roster, approves trades through the real manager, and gives a
crunch forecast with counts only. Run: uvicorn steward.app:app --port 8701
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.net import Net, registry
from core.timeutil import fmt_span
from core.wire import BusyBits, Decision, Move, OpenShift, Prepare, ShiftRef, SlotQuery, Vote
from ingest.ics import read, shifts_from_ics
from seeds.scenario import DEMO_MONDAY, EMPLOYER, STUDENTS

ICS = Path(__file__).resolve().parent.parent / "seeds" / "ics"
K_ANON = 3  # the forecast only reports a slot when at least this many people are affected


class Tap(BaseModel):
    data: str


def load_roster() -> dict[str, ShiftRef]:
    roster: dict[str, ShiftRef] = {}
    start, end = DEMO_MONDAY - timedelta(days=7), DEMO_MONDAY + timedelta(days=14)
    for s in STUDENTS:
        for sh in shifts_from_ics(read(ICS / f"{s['id']}_library.ics"), EMPLOYER, start, end):
            roster[sh.id] = ShiftRef(shift_id=sh.id, employer=EMPLOYER, start=sh.start, end=sh.end, owner=s["id"])
    return roster


def create_app(net: Net | None = None, reg: dict | None = None) -> FastAPI:
    app = FastAPI(title="Tag Out steward (Library)")
    reg = reg or registry()
    app.state.net = net or Net()
    names = {s["id"]: s["name"] for s in STUDENTS}
    state = {"roster": load_roster(), "version": 1, "holds": {}, "phone": [],
             "auto": os.environ.get("TAGOUT_MODE", "auto") == "auto",
             "delay": float(os.environ.get("TAGOUT_AUTO_DELAY", "1.5")) + 0.5, "open": []}
    app.state.s = state

    async def to_manager(text: str, buttons: list[tuple[str, str]]) -> None:
        msg = {"kind": "approve", "text": text, "buttons": [{"label": a, "data": b} for a, b in buttons]}
        state["phone"].append(msg)
        try:
            await app.state.net.post(f"{reg['bot']}/send", {"student_id": "manager", **msg})
        except Exception:
            pass
        if state["auto"] and buttons:
            async def later() -> None:
                await asyncio.sleep(state["delay"])
                await handle_tap(buttons[0][1])
            asyncio.create_task(later())

    async def handle_tap(data: str) -> str:
        verb, _, txn = data.partition(":")
        if txn not in state["holds"]:
            return "That request is closed."
        vote = "yes" if verb == "approve" else "no"
        await app.state.net.post(f"{reg['broker']}/txn/vote", Vote(txn_id=txn, agent_id="steward", vote=vote))
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
                return {"vote": Vote(txn_id=p.txn_id, agent_id="steward", vote="stale").model_dump()}
        state["holds"][p.txn_id] = [m.model_dump() for m in p.moves]
        lines = [f"{names[m.from_agent]}'s {fmt_span(state['roster'][m.shift_id].start, state['roster'][m.shift_id].end)}"
                 f" -> {names[m.to_agent]}" for m in p.moves]
        text = ("Trade request: " + "; ".join(lines) + ". Each student's mascot checked its own student's work "
                "limits privately and said eligible. It goes through only if every student confirms and you approve.")
        await to_manager(text, [("Approve", f"approve:{p.txn_id}"), ("Deny", f"deny:{p.txn_id}")])
        return {"vote": None}

    @app.post("/txn/decide")
    async def decide(d: Decision) -> dict:
        moves = state["holds"].pop(d.txn_id, None)
        if moves and d.outcome == "commit":
            for m in map(lambda x: Move(**x), moves):
                ref = state["roster"][m.shift_id]
                state["roster"][m.shift_id] = ref.model_copy(update={"owner": m.to_agent})
            state["version"] += 1
        return {}

    @app.post("/open")
    async def post_open(body: OpenShift) -> dict:
        """A shift no trade could fill: the manager sees it as open, with no reason attached."""
        sid = body.shift_id
        if sid in state["roster"] and sid not in state["open"]:
            state["open"].append(sid)
            ref = state["roster"][sid]
            await to_manager(f"Open shift: {fmt_span(ref.start, ref.end)} (was {names[ref.owner]}'s). "
                             "No safe trade this week. Post it or cover it?", [])
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
        state.update(roster=load_roster(), version=1, holds={}, phone=[], open=[])
        return {"ok": True}

    @app.post("/admin/auto")
    async def auto(body: dict) -> dict:
        state["auto"] = bool(body.get("enabled", True))
        state["delay"] = float(body.get("delay", state["delay"]))
        return {"auto": state["auto"]}

    @app.get("/forecast")
    async def forecast(monday: str | None = None) -> dict:
        """Next week's crunch: for each roster slot, how many staff are busy. Counts only, k >= 3."""
        mon = datetime.fromisoformat(monday).date() if monday else DEMO_MONDAY
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
