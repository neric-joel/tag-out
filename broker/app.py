"""Broker process: trade rounds, two-phase commit, the public event stream and the arena.

Run: TAGOUT_ROLE=broker uvicorn broker.app:app --port 8700
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from broker.engine import Engine, Timing
from core.events import Bus
from core.net import RUNTIME, Net, registry
from core.timeutil import PHX, coming_monday, planning_monday
from core.wire import CallOut, Move, RingCheck, ShiftRef, SundayCheck, TradeRequest, Vote
from core.wiretap import describe
from seeds.scenario import BREAK_IT_EDIT, STUDENTS

WEB = Path(__file__).resolve().parent.parent / "web"
PETS = WEB / "pets"
mimetypes.add_type("image/webp", ".webp")  # Windows has no default type for it


def create_app(net: Net | None = None, reg: dict | None = None, timing: Timing | None = None,
               log: Path | None = None) -> FastAPI:
    app = FastAPI(title="Tag Out broker")
    reg = reg or registry()
    net = net or Net()
    bus = Bus(log if log is not None else RUNTIME / "events.jsonl")
    engine = Engine(net, reg, bus, timing or Timing())
    app.state.engine, app.state.bus, app.state.net = engine, bus, net
    net.hook = lambda m, u, p, s, b: bus.emit("wire", **describe(reg, m, u, p, s, b))
    tasks: set[asyncio.Task] = set()

    run_lock = asyncio.Lock()  # one run at a time: the Sunday week, then any same-day call-out rounds

    def spawn(coro) -> None:
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    def debug() -> bool:
        return os.environ.get("TAGOUT_DEBUG") == "1"

    # ----- agent-facing -----
    @app.post("/trade")
    async def trade(t: TradeRequest) -> dict:
        engine.request(t.agent_id, t.shift_id, urgent=t.urgent)
        if t.urgent:
            spawn(net.post(f"{reg['steward']}/callout", CallOut(shift_id=t.shift_id)))  # the manager hears now
            if "jordan" in reg.get("org", {}):  # and the Library's shift lead, who sees the case on the org chart
                spawn(net.post(f"{reg['org']['jordan']}/callout", CallOut(shift_id=t.shift_id)))
            spawn(callout_round())
        return {}

    async def callout_round() -> None:
        """A same-day call-out doesn't wait for Sunday. Call-outs that land within half a second share a round."""
        await asyncio.sleep(0.5)
        async with run_lock:
            if any(s not in engine.closed and s not in engine.resolved for s in engine.requests):
                await engine.run(kind="callout")

    @app.post("/extra")
    async def extra(ref: ShiftRef) -> dict:
        """The Steward posts an extra shift the manager wants filled; every mascot gets offered it."""
        async def go() -> None:
            async with run_lock:
                await engine.offer_extra(ref)
        spawn(go())
        return {}

    @app.post("/manager/{action}")
    async def manager_action(action: str, body: dict) -> dict:
        """The manager's own screen, relayed to the Steward (synthetic demo: the manager channel)."""
        if action not in ("extra", "meeting", "tap"):
            raise HTTPException(404)
        return await net.post(f"{reg['steward']}/manager/{action}" if action != "tap" else f"{reg['steward']}/tap",
                              body)

    @app.get("/manager/state")
    async def manager_state() -> JSONResponse:
        return JSONResponse(await net.get(f"{reg['steward']}/manager/state"))

    @app.post("/admin/wire")
    async def wire(body: dict) -> dict:
        """Peer messages the other processes sent (debug only), for the judge view's agent graph."""
        if not debug():
            raise HTTPException(403)
        bus.emit("wire", **describe(reg, str(body.get("method", "POST")), str(body["url"]), body.get("payload"),
                                    int(body.get("status", 0)), body.get("response"), sender=body.get("sender")))
        return {}

    @app.post("/admin/event")
    async def org_event(body: dict) -> dict:
        """Events from the campus hierarchy's process (scripts/run_org.py), for the org chart (debug only)."""
        if not debug() or not str(body.get("type", "")).startswith("org_"):
            raise HTTPException(403)
        bus.emit(body.pop("type"), **body)
        return {}

    @app.post("/demo/snoop")
    async def snoop() -> dict:
        """The judge plays a nosy broker: ask every mascot why it passed, then probe for room it never offered.
        The closed schemas reject the first, and a mascot only vouches for shifts it picked, so both get nothing."""
        if not debug():
            raise HTTPException(403)
        await engine.load_roster()
        out = {}
        for a, url in reg["agents"].items():
            nosy = {"round_id": "snoop", "iteration": 1, "phase": "cover", "items": [], "why_did_you_pass": True}
            r = await net.client.post(f"{url}/round/pick", json=nosy)
            net._tap("POST", f"{url}/round/pick", nosy, r)
            other = next((s for s in engine.roster.values() if s.owner != a), None)
            ok = None
            if other is not None:
                probe = RingCheck(ring_id="snoop", moves=[Move(shift_id=other.shift_id, from_agent=other.owner,
                                                               to_agent=a)])
                ok = (await net.post(f"{url}/ring/check", probe)).get("ok")
            out[a] = {"why": r.status_code, "room_probe": ok}
        bus.emit("snoop", results=out)
        return out

    @app.post("/txn/vote")
    async def vote(v: Vote) -> dict:
        await engine.vote(v)
        return {}

    # ----- public -----
    @app.get("/events")
    async def events(last_event_id: str | None = Header(None)):
        q = bus.subscribe()
        seen = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
        if seen > len(bus.history):
            seen = 0  # the demo was reset since: send everything

        async def gen():
            try:
                for ev in list(bus.history)[seen:]:
                    yield {"id": str(ev["n"]), "data": json.dumps(ev, default=str)}
                while True:
                    ev = await q.get()
                    yield {"id": str(ev["n"]), "data": json.dumps(ev, default=str)}
            finally:
                bus.unsubscribe(q)

        return EventSourceResponse(gen(), ping=15)

    @app.get("/state")
    async def state() -> dict:
        faces = {}
        for aid, url in reg["agents"].items():
            try:
                faces[aid] = await net.get(f"{url}/public")
            except Exception:
                faces[aid] = {"agent_id": aid, "name": aid.title(), "pet_id": "debug-duck-v2", "state": "idle",
                              "trades_made": 0, "badges": []}
        try:
            roster = await net.get(f"{reg['steward']}/roster")
        except Exception:
            roster = []
        return {"agents": faces, "roster": roster, "summary": engine.summary, "running": engine.running,
                "monday": planning_monday().isoformat(), "debug": debug(),
                "pets": json.loads((WEB.parent / "seeds" / "pets.json").read_text(encoding="utf-8"))}

    @app.get("/agents")
    async def agents() -> dict:
        return {"agents": reg["agents"], "steward": reg["steward"], "names": {s["id"]: s["name"] for s in STUDENTS}}

    def who_url(who: str) -> str:
        if who == "manager":
            return reg["steward"]
        url = reg["agents"].get(who) or reg.get("org", {}).get(who)
        if url is None:
            raise HTTPException(404)
        return url

    @app.get("/org")
    async def org() -> dict:
        """The campus hierarchy (seeds/org.py) for the org chart: people, rungs, open cases and each inbox."""
        from seeds.org import ALSO, DEPARTMENTS, ORG_STUDENTS, ROLES

        urls = reg.get("org", {})
        roles = {}
        for r, spec in ROLES.items():
            if r == "steward" or r not in urls:
                continue
            try:
                roles[r] = await net.get(f"{urls[r]}/state")
            except Exception:
                roles[r] = {"id": r, **spec, "cases": [], "phone": []}
        try:
            mgr = (await net.get(f"{reg['steward']}/phone"))["messages"]
        except Exception:
            mgr = []
        roles["steward"] = {"id": "steward", **ROLES["steward"], "cases": [], "phone": mgr}

        async def face(sid: str, url: str) -> dict:
            try:
                return await net.get(f"{url}/public")
            except Exception:
                return {"agent_id": sid, "name": sid.title(), "pet_id": "debug-duck-v2"}
        lib = [{"id": s["id"], "dept": "library", "also": ALSO.get(s["id"], [])} for s in STUDENTS]
        new = [{"id": s["id"], "dept": s["dept"], "also": []} for s in ORG_STUDENTS if s["id"] in urls]
        people = []
        for p in lib + new:
            f = await face(p["id"], reg["agents"].get(p["id"]) or urls[p["id"]])
            people.append({**p, "name": f["name"], "pet_id": f["pet_id"]})
        return {"departments": DEPARTMENTS, "students": people, "roles": roles}

    # ----- demo controls (synthetic roster) -----
    @app.post("/demo/sunday")
    async def sunday(monday: str | None = None) -> dict:
        week = datetime.fromisoformat(monday).date() if monday else planning_monday()
        await asyncio.gather(*(net.post(f"{u}/sunday", SundayCheck(monday=week))
                               for u in reg["agents"].values()), return_exceptions=True)
        bus.emit("sunday_check", monday=week.isoformat(), agents=sorted(reg["agents"]))
        return {}

    @app.post("/demo/run")
    async def run(body: dict | None = None) -> dict:
        wait = float((body or {}).get("wait", 0))

        async def go() -> None:
            if wait:
                await asyncio.sleep(wait)
            await run_week()

        spawn(go())
        return {"started": True}

    @app.post("/demo/org/{which}")
    async def org_demo(which: str) -> dict:
        """The org chart's buttons, live: the student texts their own mascot, and the hierarchy takes it from there.
        "morning" runs all three, one after another."""
        from seeds.org import ORG_DEMO

        if not debug() or (which not in ORG_DEMO and which != "morning"):
            raise HTTPException(404)

        async def one(key: str) -> None:
            who, text = ORG_DEMO[key]
            n = len(bus.history)
            await net.post(f"{who_url(who)}/intake", {"text": text})
            for _ in range(1200):  # wait for that case to close before the next text
                if any(e["type"] in ("org_done", "org_overdue") for e in bus.history[n:]):
                    return
                await asyncio.sleep(0.1)

        async def go() -> None:
            for key in (ORG_DEMO if which == "morning" else [which]):
                await one(key)
                await asyncio.sleep(1.0)
        spawn(go())
        return {"started": which}

    @app.post("/demo/break")
    async def break_it() -> dict:
        """The judge edits Dev's week while the ring waits for confirmations."""
        if not debug():
            raise HTTPException(403)
        e = BREAK_IT_EDIT
        r = await net.post(f"{reg['agents'][e['student']]}/intake", {"text": e["text"]})
        bus.emit("schedule_edited", agent=e["student"])
        return {"ok": True, "engine": r.get("engine")}

    @app.post("/admin/reset")
    async def reset() -> dict:
        if not debug():
            raise HTTPException(403)
        engine.reset()
        app.state.baseline = None
        bus.clear()
        others = [u for r, u in reg.get("org", {}).items() if r != "steward"]  # the campus hierarchy and its mascots
        await asyncio.gather(*(net.post(f"{u}/admin/reset") for u in list(reg["agents"].values())
                               + [reg["steward"]] + others), return_exceptions=True)
        bus.emit("reset")
        return {"ok": True}

    @app.post("/admin/auto")
    async def auto(body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        targets = body.get("agents") or list(reg["agents"])
        await asyncio.gather(*(net.post(f"{reg['agents'][a]}/admin/auto", body) for a in targets),
                             return_exceptions=True)
        if body.get("steward", True) and not body.get("agents"):
            await net.post(f"{reg['steward']}/admin/auto", body)
        return {"ok": True}

    @app.post("/admin/timing")
    async def set_timing(body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        for k in ("pick_deadline", "ask_window", "vote_timeout", "between"):
            if k in body:
                setattr(engine.timing, k, float(body[k]))
        return engine.timing.__dict__

    @app.get("/admin/judge")
    async def judge() -> dict:
        if not debug():
            raise HTTPException(403)
        out = {}
        for aid, url in reg["agents"].items():
            try:
                out[aid] = await net.get(f"{url}/admin/debug")
            except Exception:
                pass
        return out

    @app.get("/phone/{who}")
    async def phone(who: str, since: int = 0) -> JSONResponse:
        """Judge view relays each phone from its own mascot (synthetic demo only)."""
        if not debug():
            raise HTTPException(403)
        return JSONResponse(await net.get(f"{who_url(who)}/phone?since={since}"))

    @app.get("/me/{who}")
    async def me(who: str) -> JSONResponse:
        """A student's own page (synthetic demo: relayed from their mascot's owner channel)."""
        if not debug() or who == "manager":
            raise HTTPException(403)
        return JSONResponse(await net.get(f"{who_url(who)}/diary"))

    @app.get("/quotes")
    async def quotes() -> JSONResponse:
        return JSONResponse(json.loads((WEB.parent / "docs" / "rule_quotes.json").read_text(encoding="utf-8")))

    @app.post("/phone/{who}/tap")
    async def phone_tap(who: str, body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        return await net.post(f"{who_url(who)}/tap", {"data": body["data"]})

    @app.post("/phone/{who}/text")
    async def phone_text(who: str, body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        return await net.post(f"{who_url(who)}/intake", {"text": body["text"]})

    # ----- pet gallery (Codex Pets): search, download on demand, assign to a student -----
    gallery = "https://codex-pets.net"

    @app.get("/pets/search")
    async def pets_search(q: str = "", page: int = 1) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{gallery}/api/pets", params={"page": max(1, page), "pageSize": 12, "q": q[:60]})
            r.raise_for_status()
            d = r.json()
        local = {p.name for p in PETS.iterdir() if (p / "spritesheet.webp").exists()} if PETS.exists() else set()
        return {"total": d.get("total", 0), "page": d.get("page", page), "pets": [{
            "id": p["id"], "name": p.get("displayName") or p["id"], "creator": p.get("ownerName") or "",
            "version": p.get("spriteVersionNumber", 1), "poster": p.get("posterUrl"), "sheet": p.get("spritesheetUrl"),
            "page": f"{gallery}/#/pets/{p['id']}", "downloaded": p["id"] in local} for p in d.get("pets", [])]}

    @app.post("/pets/use")
    async def pets_use(body: dict) -> dict:
        """Give a student a pet: download its sprite sheet if needed, then set it on their mascot."""
        if not debug():
            raise HTTPException(403)
        agent, pet_id, sheet = body.get("agent"), str(body.get("pet_id", "")), body.get("sheet") or ""
        if agent not in reg["agents"] or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", pet_id):
            raise HTTPException(400, "unknown student or pet")
        faces = {a: (await net.get(f"{u}/public"))["pet_id"] for a, u in reg["agents"].items()}
        taken = next((a for a, pid in faces.items() if pid == pet_id and a != agent), None)
        if taken:
            raise HTTPException(409, f"{taken.title()} already has that pet; no two people on a roster share one")
        target = PETS / pet_id / "spritesheet.webp"
        if not target.exists():
            if not sheet.startswith(f"{gallery}/assets/"):
                raise HTTPException(400, "sprite sheets only come from codex-pets.net")
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as c:
                r = await c.get(sheet)
                r.raise_for_status()
            if len(r.content) > 12_000_000:
                raise HTTPException(413, "sprite sheet too large")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(r.content)
        await net.post(f"{reg['agents'][agent]}/pet", {"pet_id": pet_id})
        bus.emit("pet_changed", agent=agent, pet_id=pet_id)
        return {"ok": True, "agent": agent, "pet_id": pet_id}

    @app.get("/roster.csv")
    async def roster_csv():
        r = await net.client.get(f"{reg['steward']}/export.csv")
        return Response(r.content, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=library-roster.csv"})

    @app.get("/roster.ics")
    async def roster_ics():
        r = await net.client.get(f"{reg['steward']}/export.ics")
        return Response(r.content, media_type="text/calendar",
                        headers={"Content-Disposition": "attachment; filename=library-roster.ics"})

    app.state.baseline = None  # computed once, on the week as it stood before any trade

    @app.get("/admin/baseline")
    async def baseline() -> dict:
        """Judge view: the same week handled by a Library-only scheduler that sees availability and Library hours,
        like a typical shift app, but not other jobs or anyone's limits. Uses the synthetic students' private
        numbers only to show what that scheduler would break."""
        if not debug():
            raise HTTPException(403)
        if app.state.baseline is not None:
            return app.state.baseline
        return await compute_baseline()

    async def compute_baseline() -> dict:
        roster = {r["shift_id"]: r for r in await net.get(f"{reg['steward']}/roster")}
        requested = engine.requests or {}
        if not requested:
            return {"rows": [], "note": "Run the Sunday check first."}
        private = {a: await net.get(f"{u}/admin/debug") for a, u in reg["agents"].items()}
        library_hours = {a: 0.0 for a in reg["agents"]}
        for r in roster.values():
            if planning_monday().isoformat() <= r["start"][:10] < (planning_monday() + timedelta(days=7)).isoformat():
                library_hours[r["owner"]] = library_hours.get(r["owner"], 0) + 4
        rows, taken = [], set()
        for sid, owner in sorted(requested.items(), key=lambda kv: roster[kv[0]]["start"]):
            ref = roster[sid]
            st, en = datetime.fromisoformat(ref["start"]), datetime.fromisoformat(ref["end"])
            key = f"{st:%a} {st.hour}-{en.hour}"  # same slot naming as the manager's crunch forecast
            slots = {key: (ref["start"], ref["end"])}
            free = []
            for a, u in reg["agents"].items():
                if a == owner or a in taken:
                    continue
                if any(o["owner"] == a and o["start"] < ref["end"] and ref["start"] < o["end"] for o in roster.values()):
                    continue
                bits = await net.post(f"{u}/busybits", {"slots": slots})
                if not bits["slots"][key]:
                    lib_cap = 20 if private[a]["f1"] else 40  # the Library only knows its own hours
                    if library_hours[a] + 4 <= lib_cap:
                        free.append(a)
            if not free:
                rows.append({"shift_id": sid, "owner": owner, "to": None, "library_view": None, "real": None,
                             "breaks": None})
                continue
            pick = min(free, key=lambda a: (library_hours[a], a))  # fewest Library hours first
            taken.add(pick)
            p = private[pick]
            real_total = p["week_hours"] + 4
            breaks = []
            for room in p["rooms"]:
                left = room["room"] - (64 if room["unit"] == "$" else 4)
                if left < 0:
                    breaks.append(room["rule_id"])
            rows.append({"shift_id": sid, "owner": owner, "to": pick, "library_view": library_hours[pick] + 4,
                         "real": real_total, "breaks": breaks})
            library_hours[pick] += 4
        return {"rows": rows, "pay_lost": 64 * sum(1 for r in rows if r["to"]),
                "violations": sum(1 for r in rows if r["breaks"])}

    async def run_week() -> None:
        async with run_lock:
            if debug() and app.state.baseline is None and engine.requests:
                try:
                    app.state.baseline = await compute_baseline()
                except Exception as e:  # the comparison is judge-view only; never block the real rounds on it
                    bus.emit("baseline_error", error=type(e).__name__)
            await engine.run()

    @app.get("/sim")
    async def sim() -> JSONResponse:
        path = WEB.parent / "docs" / "simulation.json"
        if not path.exists():
            raise HTTPException(404, "run python -m sim.simulate")
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/forecast")
    async def forecast() -> dict:
        """The Steward's crunch forecast (counts only), relayed for the dashboard."""
        return await net.get(f"{reg['steward']}/forecast")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.get("/judge")
    async def judge_page() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.on_event("startup")
    async def sunday_scheduler() -> None:
        """Every Sunday at 6 PM Arizona time: the Sunday check, then trade rounds 10 minutes later.
        On by default in live mode; TAGOUT_SCHEDULE=0 turns it off, =1 forces it on."""
        on = os.environ.get("TAGOUT_SCHEDULE", "1" if os.environ.get("TAGOUT_MODE") == "live" else "0") == "1"
        if not on:
            return

        async def loop() -> None:
            last = None
            while True:
                now = datetime.now(PHX)
                if now.weekday() == 6 and now.hour == 18 and last != now.date():
                    last = now.date()
                    bus.emit("scheduled", what="sunday_check")
                    week = planning_monday() if os.environ.get("TAGOUT_WEEK") else coming_monday(now)
                    await sunday(week.isoformat())
                    await asyncio.sleep(600)
                    await run_week()
                await asyncio.sleep(30)

        spawn(loop())

    if WEB.exists():
        app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app


def _timing_from_env() -> Timing:
    if os.environ.get("TAGOUT_FAST") == "1":
        return Timing.fast()
    return Timing.live() if os.environ.get("TAGOUT_MODE") == "live" else Timing()


app = create_app(timing=_timing_from_env()) if os.environ.get("TAGOUT_ROLE") == "broker" else None
