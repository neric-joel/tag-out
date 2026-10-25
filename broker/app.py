"""Broker process: trade rounds, two-phase commit, the public event stream and the arena.

Run: TAGOUT_ROLE=broker uvicorn broker.app:app --port 8700
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from broker.engine import Engine, Timing
from core.events import Bus
from core.net import RUNTIME, Net, registry
from core.wire import SundayCheck, TradeRequest, Vote
from seeds.scenario import BREAK_IT_EDIT, DEMO_MONDAY, STUDENTS

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
    tasks: set[asyncio.Task] = set()

    def spawn(coro) -> None:
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    def debug() -> bool:
        return os.environ.get("TAGOUT_DEBUG") == "1"

    # ----- agent-facing -----
    @app.post("/trade")
    async def trade(t: TradeRequest) -> dict:
        engine.request(t.agent_id, t.shift_id)
        return {}

    @app.post("/txn/vote")
    async def vote(v: Vote) -> dict:
        await engine.vote(v)
        return {}

    # ----- public -----
    @app.get("/events")
    async def events():
        q = bus.subscribe()

        async def gen():
            try:
                for ev in list(bus.history):
                    yield {"data": json.dumps(ev, default=str)}
                while True:
                    ev = await q.get()
                    yield {"data": json.dumps(ev, default=str)}
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
                "monday": DEMO_MONDAY.isoformat(), "debug": debug(),
                "pets": json.loads((WEB.parent / "seeds" / "pets.json").read_text(encoding="utf-8"))}

    @app.get("/agents")
    async def agents() -> dict:
        return {"agents": reg["agents"], "steward": reg["steward"], "names": {s["id"]: s["name"] for s in STUDENTS}}

    # ----- demo controls (synthetic roster) -----
    @app.post("/demo/sunday")
    async def sunday() -> dict:
        await asyncio.gather(*(net.post(f"{u}/sunday", SundayCheck(monday=DEMO_MONDAY))
                               for u in reg["agents"].values()), return_exceptions=True)
        bus.emit("sunday_check", monday=DEMO_MONDAY.isoformat(), agents=sorted(reg["agents"]))
        return {}

    @app.post("/demo/run")
    async def run(body: dict | None = None) -> dict:
        wait = float((body or {}).get("wait", 0))

        async def go() -> None:
            if wait:
                await asyncio.sleep(wait)
            await engine.run()

        spawn(go())
        return {"started": True}

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
        bus.clear()
        await asyncio.gather(*(net.post(f"{u}/admin/reset") for u in list(reg["agents"].values())
                               + [reg["steward"]]), return_exceptions=True)
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
        url = reg["steward"] if who == "manager" else reg["agents"][who]
        return JSONResponse(await net.get(f"{url}/phone?since={since}"))

    @app.post("/phone/{who}/tap")
    async def phone_tap(who: str, body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        url = reg["steward"] if who == "manager" else reg["agents"][who]
        return await net.post(f"{url}/tap", {"data": body["data"]})

    @app.post("/phone/{who}/text")
    async def phone_text(who: str, body: dict) -> dict:
        if not debug():
            raise HTTPException(403)
        return await net.post(f"{reg['agents'][who]}/intake", {"text": body["text"]})

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

    if WEB.exists():
        app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app


def _timing_from_env() -> Timing:
    if os.environ.get("TAGOUT_FAST") == "1":
        return Timing.fast()
    return Timing.live() if os.environ.get("TAGOUT_MODE") == "live" else Timing()


app = create_app(timing=_timing_from_env()) if os.environ.get("TAGOUT_ROLE") == "broker" else None
