"""One mascot = one process = one SQLite file. Run: TAGOUT_STUDENT=ana uvicorn agents.mascot:app --port 8711

Peer-facing endpoints accept and return only core.wire schemas. Owner endpoints (phone, diary, intake, tap) need the
owner token, or TAGOUT_DEBUG=1 for the synthetic demo.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from agents.brain import Brain
from agents.seed import seed
from agents.store import Store
from core.models import BusyBlock
from core.net import RUNTIME, Net, registry
from core.timeutil import PHX, fmt_span, overlaps, planning_monday
from core.wire import (
    BusyBits,
    Decision,
    Eligibility,
    NoTrade,
    Pick,
    PickRequest,
    Prepare,
    PublicFace,
    RingCheck,
    SlotQuery,
    SundayCheck,
    TradeRequest,
    VersionReport,
    Vote,
)
from ingest import text as text_intake
from ingest.ics import _bid, classify, exam_eves
from seeds.scenario import STUDENTS


class Tap(BaseModel):
    data: str


class Intake(BaseModel):
    text: str


class ImportedEvent(BaseModel):
    title: str
    start: datetime
    end: datetime | None = None
    kind: str = "other"


class EventImport(BaseModel):
    source: Literal["canvas", "calendar"]
    events: list[ImportedEvent]


class PetChoice(BaseModel):
    pet_id: str


class Auto(BaseModel):
    enabled: bool
    delay: float = 1.5


def debug() -> bool:
    return os.environ.get("TAGOUT_DEBUG") == "1"


def create_app(sid: str, db_path: str | None = None, net: Net | None = None, reg: dict | None = None) -> FastAPI:
    app = FastAPI(title=f"Tag Out mascot: {sid}")
    store = Store(db_path or RUNTIME / f"mascot_{sid}.db")
    reg = reg or registry()
    app.state.net = net or Net()
    app.state.auto = {"enabled": os.environ.get("TAGOUT_MODE", "auto") == "auto",
                      "delay": float(os.environ.get("TAGOUT_AUTO_DELAY", "1.5"))}
    names = {s["id"]: s["name"] for s in STUDENTS} | {"steward": "Library manager"}
    if store.get("student") is None:
        seed(store, sid)
    owner_token = store.get("owner_token") or secrets.token_urlsafe(16)
    store.put("owner_token", owner_token)
    if db_path is None:  # a real process: leave the token where only this machine's bot can read it
        (RUNTIME / "tokens").mkdir(parents=True, exist_ok=True)
        (RUNTIME / "tokens" / f"{sid}.txt").write_text(owner_token)

    async def to_phone(msg: dict) -> None:
        try:
            await app.state.net.post(f"{reg['bot']}/send", {"student_id": sid, **msg})
        except Exception:
            pass  # no bot running: the message is still on this mascot's own phone view
        if app.state.auto["enabled"] and msg.get("buttons"):
            yes = next((b["data"] for b in msg["buttons"]
                        if b["data"].startswith(("ask:yes", "confirm:", "trade:yes"))), msg["buttons"][0]["data"])
            task = asyncio.create_task(auto_tap(yes))
            brain.auto_tasks.add(task)
            task.add_done_callback(brain.auto_tasks.discard)

    async def auto_tap(data: str) -> None:
        await asyncio.sleep(app.state.auto["delay"])
        if app.state.auto["enabled"]:
            reply = await brain.tap(data)
            store.send({"kind": "reply", "text": reply, "buttons": [], "from": "auto"})

    async def send_vote(v: Vote) -> None:
        await app.state.net.post(f"{reg['broker']}/txn/vote", v)

    async def send_trade(t: TradeRequest) -> None:
        await app.state.net.post(f"{reg['broker']}/trade", t)

    brain = Brain(store, to_phone, send_vote, send_trade, lambda: names)
    app.state.brain, app.state.store = brain, store

    def owner(token: str | None) -> None:
        if not debug() and token != store.get("owner_token"):
            raise HTTPException(403, "owner only")

    # ----- peer-facing (wire schemas only) -----
    @app.post("/round/pick", response_model=Pick)
    async def round_pick(req: PickRequest) -> Pick:
        return await brain.pick(req)

    @app.post("/ring/check", response_model=Eligibility)
    async def ring_check(rc: RingCheck) -> Eligibility:
        return brain.check(rc)

    @app.get("/version", response_model=VersionReport)
    async def version() -> VersionReport:
        return VersionReport(agent_id=sid, version=store.version())

    @app.post("/txn/prepare")
    async def prepare(p: Prepare) -> dict:
        v = await brain.prepare(p)
        return {"vote": v.model_dump() if v else None}

    @app.post("/txn/decide")
    async def decide(d: Decision) -> dict:
        await brain.decide(d)
        return {}

    @app.post("/sunday")
    async def sunday(body: SundayCheck) -> dict:
        await brain.sunday_check(body.monday)
        return {}  # the broker learns nothing about how many collisions there were

    @app.post("/round/none")
    async def no_trade(body: NoTrade) -> dict:
        s = store.shift(body.shift_id)
        if s:
            store.note(f"No safe trade for {s.label} this week; it stays on your schedule.")
            await brain.notify(f"No trade worked for your {s.label} shift this week, so it's still yours. If you "
                               "can't work it, ask your manager for the time off; I've told them it's open for a "
                               "trade, with no reason.", kind="info")
        return {}

    @app.get("/public", response_model=PublicFace)
    async def public() -> PublicFace:
        return brain.public_face()

    @app.post("/busybits", response_model=BusyBits)
    async def busybits(body: SlotQuery) -> BusyBits:
        """One bit per roster slot for the manager's crunch forecast (counted only when 3+ people)."""
        busy = store.busy()
        slots = {k: any(overlaps(st, en, b.start, b.end) for b in busy) for k, (st, en) in body.slots.items()}
        return BusyBits(agent_id=sid, slots=slots)

    @app.get("/.well-known/agent-card.json")
    async def agent_card(request: Request) -> dict:
        base = str(request.base_url).rstrip("/")
        return {
            "name": f"{names[sid]}'s Tag Out mascot",
            "description": "Personal scheduling agent for one student worker. Trades shifts by pick or pass only.",
            "version": "0.1.0",
            "supported_interfaces": [{"url": base, "transport": "HTTP+JSON"}],
            "capabilities": {"streaming": False, "pushNotifications": False},
            "default_input_modes": ["application/json"],
            "default_output_modes": ["application/json"],
            "skills": [
                {"id": "pick", "name": "Answer a trade round", "description": "Returns one shift id or a pass.",
                 "tags": ["ttc", "shift-trade"], "examples": ["POST /round/pick"]},
                {"id": "ring-check", "name": "Check a final ring", "description": "Returns ok true/false only.",
                 "tags": ["validation"], "examples": ["POST /ring/check"]},
                {"id": "two-phase-commit", "name": "Prepare and commit a trade",
                 "description": "Holds shifts, asks its student, votes yes/no/stale.", "tags": ["2pc"],
                 "examples": ["POST /txn/prepare", "POST /txn/decide"]},
            ],
        }

    # ----- owner channel -----
    @app.post("/tap")
    async def tap(t: Tap, x_owner_token: str | None = Header(None)) -> dict:
        owner(x_owner_token)
        reply = await brain.tap(t.data)
        store.send({"kind": "reply", "text": reply, "buttons": []})
        return {"reply": reply}

    @app.post("/intake")
    async def intake(body: Intake, x_owner_token: str | None = Header(None)) -> dict:
        owner(x_owner_token)
        store.send({"kind": "student", "text": body.text, "buttons": []})
        want = text_intake.callout(body.text, planning_monday(), datetime.now(PHX).date())
        if want is not None:
            reply = await brain.call_out(want, planning_monday())
            store.send({"kind": "reply", "text": reply, "buttons": [], "engine": "callout"})
            return {"reply": reply, "engine": "callout", "events": 0}
        parsed, engine = text_intake.parse(body.text, planning_monday())
        blocks = text_intake.to_blocks(parsed)
        from agents.seed import merge_prefs
        store.add_busy(blocks)
        store.save_student(merge_prefs(store.student(), parsed.get("preferences") or {}))
        await brain.schedule_changed()
        got = ", ".join(f"{b.label} {fmt_span(b.start, b.end)}" for b in blocks) or "your preferences"
        reply = f"Noted: {got}. Only 'busy' ever leaves me."
        store.send({"kind": "reply", "text": reply, "buttons": [], "engine": engine})
        return {"reply": reply, "engine": engine, "events": len(blocks)}

    @app.post("/import")
    async def import_events(body: EventImport, x_owner_token: str | None = Header(None)) -> dict:
        """Calendar items from the student's own assistant (Cubbie reads Canvas and Google Calendar and sends them
        here). They become private busy blocks; the label never leaves this mascot."""
        owner(x_owner_token)
        blocks = []
        for e in body.events[:500]:
            kind = e.kind if e.kind in text_intake.KINDS else classify(e.title)
            if body.source == "canvas" and kind in ("other", "class"):
                kind = "due"
            end = e.end if e.end and e.end > e.start else e.start + timedelta(hours=1 if kind != "due" else 0)
            blocks.append(BusyBlock(id=_bid(body.source, e.title, e.start), start=e.start, end=max(end, e.start),
                                    kind=kind, label=e.title[:80], source=body.source))  # type: ignore[arg-type]
        if body.source == "canvas" and store.student().prefs.protect_exam_eves:
            blocks += exam_eves(blocks)
        store.add_busy(blocks)
        await brain.schedule_changed()
        return {"imported": len(blocks)}

    @app.post("/pet")
    async def pet(body: PetChoice, x_owner_token: str | None = Header(None)) -> dict:
        """The student's own pick. Cosmetic only; the bot keeps picks unique per roster."""
        owner(x_owner_token)
        st = store.student()
        store.save_student(st.model_copy(update={"pet_id": body.pet_id}))
        return {"reply": f"Done. Your mascot is now {body.pet_id.replace('-', ' ')}."}

    @app.get("/phone")
    async def phone(since: int = 0, x_owner_token: str | None = Header(None)) -> dict:
        owner(x_owner_token)
        return {"student": names[sid], "messages": store.outbox(since)}

    @app.get("/diary")
    async def diary(monday: str | None = None, x_owner_token: str | None = Header(None)) -> dict:
        owner(x_owner_token)
        return brain.diary(date.fromisoformat(monday) if monday else planning_monday())

    # ----- demo controls (synthetic data only) -----
    @app.post("/admin/reset")
    async def reset() -> dict:
        if not debug():
            raise HTTPException(403)
        token = store.get("owner_token")
        seed(store, sid)
        store.put("owner_token", token)
        brain.seen.clear()
        return {"ok": True}

    @app.post("/admin/auto")
    async def auto(a: Auto) -> dict:
        if not debug():
            raise HTTPException(403)
        app.state.auto = a.model_dump()
        return app.state.auto

    @app.get("/admin/debug")
    async def judge() -> dict:
        """Judge view only (red DEBUG banner): private numbers of a synthetic student."""
        if not debug():
            raise HTTPException(403)
        from rulebook.rules import rooms, week_hours
        st = store.student()
        shifts = store.shifts()
        return {
            "id": sid, "name": st.name, "f1": st.limits.f1_or_j1, "fws": st.limits.fws,
            "week_hours": week_hours(st, shifts, planning_monday()),
            "other_employers": st.limits.other_employer_hours,
            "rooms": [r.__dict__ for r in rooms(st, shifts, planning_monday())],
            "wants_more_hours": st.prefs.wants_more_hours,
        }

    return app


app = create_app(os.environ["TAGOUT_STUDENT"]) if os.environ.get("TAGOUT_STUDENT") else None
