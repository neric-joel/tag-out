"""Every agent as an ASGI app on one shared client: the whole system in one process, for tests and offline replay.

Each mascot still has its own app object and its own SQLite file; the only change is the transport.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastapi import FastAPI

from agents.mascot import create_app as mascot_app
from broker.app import create_app as broker_app
from broker.engine import Timing
from core.net import Net
from seeds.scenario import STUDENTS
from steward.app import create_app as steward_app

PEER_PATHS = ("/round/pick", "/ring/check", "/version", "/txn/prepare", "/txn/decide", "/txn/vote", "/trade",
              "/sunday", "/public", "/busybits", "/roster", "/people", "/open")


@dataclass
class Wiretap:
    """Records every agent-to-agent message (not the owner channel: phone, tap, intake, diary)."""

    frames: list[dict] = field(default_factory=list)

    async def on_request(self, request: httpx.Request) -> None:
        if request.url.path.startswith(PEER_PATHS):
            body = request.content.decode() if request.content else ""
            self.frames.append({"dir": "req", "url": str(request.url), "body": body})

    async def on_response(self, response: httpx.Response) -> None:
        if response.request.url.path.startswith(PEER_PATHS):
            await response.aread()
            self.frames.append({"dir": "resp", "url": str(response.request.url), "body": response.text})

    def dump(self) -> str:
        return "\n".join(json.dumps(f) for f in self.frames)


class System:
    def __init__(self, timing: Timing | None = None, auto_delay: float = 0.05, tmp: Path | None = None):
        os.environ["TAGOUT_DEBUG"] = "1"
        os.environ["TAGOUT_MODE"] = "auto"
        os.environ["TAGOUT_AUTO_DELAY"] = str(auto_delay)
        self.tmp = tmp or Path(tempfile.mkdtemp(prefix="tagout-"))
        self.reg = {"agents": {s["id"]: f"http://{s['id']}.mascot" for s in STUDENTS},
                    "broker": "http://broker.local", "steward": "http://steward.local", "bot": "http://bot.local"}
        self.tap = Wiretap()
        self.net = Net()
        self.apps = {s["id"]: mascot_app(s["id"], self.tmp / f"{s['id']}.db", self.net, self.reg) for s in STUDENTS}
        self.steward = steward_app(self.net, self.reg)
        self.broker = broker_app(self.net, self.reg, timing or Timing.fast(), log=self.tmp / "events.jsonl")
        mounts = {u: self.apps[a] for a, u in self.reg["agents"].items()}
        mounts[self.reg["steward"]] = self.steward
        mounts[self.reg["broker"]] = self.broker
        self.sent: list[dict] = []
        bot = FastAPI()

        @bot.post("/send")
        async def send(body: dict) -> dict:
            self.sent.append(body)
            return {}

        mounts[self.reg["bot"]] = bot
        transports = {k: httpx.ASGITransport(app=v) for k, v in mounts.items()}
        self.net.client = httpx.AsyncClient(mounts=transports, timeout=30,
                                            event_hooks={"request": [self.tap.on_request],
                                                         "response": [self.tap.on_response]})

    @property
    def engine(self):
        return self.broker.state.engine

    @property
    def bus(self):
        return self.broker.state.bus

    async def post(self, path: str, body: dict | None = None) -> dict:
        return await self.net.post(f"{self.reg['broker']}{path}", body or {})

    async def wait_for(self, type_: str, timeout: float = 20.0, after: int = 0) -> dict:
        async def poll() -> dict:
            while True:
                for ev in self.bus.history[after:]:
                    if ev["type"] == type_:
                        return ev
                await asyncio.sleep(0.02)
        return await asyncio.wait_for(poll(), timeout)

    async def settle(self, seconds: float = 0.3) -> None:
        await asyncio.sleep(seconds)

    async def sunday_and_run(self) -> dict:
        await self.post("/demo/sunday")
        await self.settle(0.4)  # students tap "Find a trade"
        return await self.engine.run()

    def phone(self, sid: str) -> list[dict]:
        return self.apps[sid].state.store.outbox()

    def store(self, sid: str):
        return self.apps[sid].state.store

    async def close(self) -> None:
        await self.net.aclose()
