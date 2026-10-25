"""One SQLite file per mascot. Only this mascot's process opens it."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models import BusyBlock, Shift, Student
from core.timeutil import PHX

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shifts (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS busy (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (n INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS diary (n INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, text TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # key/value
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value, default=str)))
        self.db.commit()

    # student
    def student(self) -> Student:
        return Student.model_validate(self.get("student"))

    def save_student(self, s: Student) -> None:
        self.put("student", s.model_dump(mode="json"))

    # schedule version: bumped on every change, so a stale trade can be caught
    def version(self) -> int:
        return int(self.get("version", 0))

    def bump(self) -> int:
        v = self.version() + 1
        self.put("version", v)
        return v

    # shifts
    def shifts(self) -> list[Shift]:
        rows = self.db.execute("SELECT json FROM shifts").fetchall()
        return sorted((Shift.model_validate_json(r[0]) for r in rows), key=lambda s: s.start)

    def shift(self, sid: str) -> Shift | None:
        row = self.db.execute("SELECT json FROM shifts WHERE id=?", (sid,)).fetchone()
        return Shift.model_validate_json(row[0]) if row else None

    def set_shifts(self, add: list[Shift], drop_ids: list[str]) -> None:
        for sid in drop_ids:
            self.db.execute("DELETE FROM shifts WHERE id=?", (sid,))
        for s in add:
            self.db.execute("INSERT OR REPLACE INTO shifts VALUES (?, ?)", (s.id, s.model_dump_json()))
        self.db.commit()

    # busy blocks (private labels)
    def busy(self) -> list[BusyBlock]:
        rows = self.db.execute("SELECT json FROM busy").fetchall()
        return sorted((BusyBlock.model_validate_json(r[0]) for r in rows), key=lambda b: b.start)

    def add_busy(self, blocks: list[BusyBlock]) -> None:
        for b in blocks:
            self.db.execute("INSERT OR REPLACE INTO busy VALUES (?, ?)", (b.id, b.model_dump_json()))
        self.db.commit()

    # messages to this student (their phone) and the private diary
    def send(self, msg: dict) -> int:
        cur = self.db.execute("INSERT INTO outbox (ts, json) VALUES (?, ?)",
                              (datetime.now(PHX).isoformat(timespec="seconds"), json.dumps(msg)))
        self.db.commit()
        return int(cur.lastrowid)

    def outbox(self, since: int = 0) -> list[dict]:
        rows = self.db.execute("SELECT n, ts, json FROM outbox WHERE n > ? ORDER BY n", (since,)).fetchall()
        return [{"n": n, "ts": ts, **json.loads(j)} for n, ts, j in rows]

    def note(self, text: str) -> None:
        self.db.execute("INSERT INTO diary (ts, text) VALUES (?, ?)", (datetime.now(PHX).isoformat(timespec="seconds"), text))
        self.db.commit()

    def diary(self, limit: int = 30) -> list[dict]:
        rows = self.db.execute("SELECT ts, text FROM diary ORDER BY n DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": ts, "text": t} for ts, t in rows]

    def reset(self) -> None:
        for t in ("kv", "shifts", "busy", "outbox", "diary"):
            self.db.execute(f"DELETE FROM {t}")
        self.db.commit()
