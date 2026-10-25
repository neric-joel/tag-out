"""HTTP between agents. Real sockets in production; in tests every agent is an ASGI app mounted on one client."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from core.wiretap import is_peer

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path(os.environ.get("TAGOUT_RUNTIME", ROOT / "runtime"))


class Net:
    def __init__(self, mounts: dict[str, Any] | None = None, timeout: float = 30.0):
        if mounts:
            transports = {k: httpx.ASGITransport(app=v) for k, v in mounts.items()}
            self.client = httpx.AsyncClient(mounts=transports, timeout=timeout)
        else:
            self.client = httpx.AsyncClient(timeout=timeout)
        # called with (method, url, payload, status, response) for every peer message this Net sends
        self.hook: Callable[[str, str, dict | None, int, Any], None] | None = None
        self.tasks: set[asyncio.Task] = set()

    async def post(self, url: str, body: BaseModel | dict | None = None) -> dict:
        payload = body.model_dump(mode="json") if isinstance(body, BaseModel) else (body or {})
        r = await self.client.post(url, json=payload)
        self._tap("POST", url, payload, r)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def get(self, url: str) -> dict:
        r = await self.client.get(url)
        self._tap("GET", url, None, r)
        r.raise_for_status()
        return r.json()

    def _tap(self, method: str, url: str, payload: dict | None, r: httpx.Response) -> None:
        if self.hook is None or not is_peer(url):
            return
        try:
            body = r.json() if r.content else None
        except ValueError:
            body = None
        self.hook(method, url, payload, r.status_code, body)

    def report_to(self, broker: str) -> None:
        """Debug only: copy each peer message this process sends to the broker's agent graph."""
        def send(method: str, url: str, payload: dict | None, status: int, body: Any) -> None:
            report = {"method": method, "url": url, "payload": payload, "status": status, "response": body}
            t = asyncio.get_running_loop().create_task(self.client.post(f"{broker}/admin/wire", json=report))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)
        self.hook = send

    async def aclose(self) -> None:
        await self.client.aclose()


def registry() -> dict:
    """Where every agent lives. Written by scripts/run_all.py; defaults match seeds/scenario.py ports."""
    path = Path(os.environ.get("TAGOUT_REGISTRY", RUNTIME / "registry.json"))
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from seeds.scenario import STUDENTS

    return {
        "agents": {s["id"]: f"http://127.0.0.1:{s['port']}" for s in STUDENTS},
        "broker": "http://127.0.0.1:8700",
        "steward": "http://127.0.0.1:8701",
        "bot": "http://127.0.0.1:8702",
    }
