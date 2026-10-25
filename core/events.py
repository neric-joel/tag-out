"""Public event stream (what the arena shows). Also written to runtime/events.jsonl so the no-leak test can scan it."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.timeutil import PHX


class Bus:
    def __init__(self, log_path: Path | None = None):
        self.subscribers: set[asyncio.Queue] = set()
        self.history: list[dict] = []
        self.log_path = log_path
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type_: str, **data: Any) -> dict:
        ev = {"n": len(self.history) + 1, "ts": datetime.now(PHX).isoformat(timespec="milliseconds"),
              "type": type_, **data}
        self.history.append(ev)
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, default=str) + "\n")
        for q in list(self.subscribers):
            q.put_nowait(ev)
        return ev

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def clear(self) -> None:
        self.history.clear()
        if self.log_path and self.log_path.exists():
            self.log_path.unlink()
