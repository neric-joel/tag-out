"""Vercel function behind the hosted page's "send your own message": runs the real system once, in one process.

POST /api/try {"who": "ben", "text": "I'm sick, can't make it Monday"} -> a recording (events, phone messages,
page snapshots) that the page replays. Nothing is kept between requests. scripts/build_site.py copies the code to
site/app/ before a deploy.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
# With ANTHROPIC_API_KEY set in the Vercel project, Claude Haiku routes and reads the visitor's text; without it,
# the regex parser and the committed cache do. Either way the rules are code, never a prompt.
os.environ.setdefault("TAGOUT_OFFLINE", "0" if os.environ.get("ANTHROPIC_API_KEY") else "1")
os.environ.setdefault("TAGOUT_SPEND_CAP", "1.0")  # per warm instance; the hard cap is the key's own spend limit
os.environ.setdefault("TAGOUT_SPEND_FILE", str(Path(tempfile.gettempdir()) / "tagout-spend.json"))
os.environ.setdefault("TAGOUT_RUNTIME", str(Path(tempfile.gettempdir()) / "tagout-runtime"))

import time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

app = FastAPI()
RECENT: dict[str, deque] = defaultdict(deque)  # per visitor: a few live runs every ten minutes
PER_10_MIN = 8


class Try(BaseModel):
    who: str
    text: str = Field(min_length=1, max_length=240)


@app.post("/api/try")
async def try_message(body: Try, request: Request) -> dict:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    now, seen = time.time(), RECENT[ip]
    while seen and now - seen[0] > 600:
        seen.popleft()
    if len(seen) >= PER_10_MIN:
        raise HTTPException(429, "That's a lot of messages; give the agents ten minutes.")
    seen.append(now)
    from scripts.record import PEOPLE
    from scripts.record import try_message as run

    if body.who not in PEOPLE:
        raise HTTPException(400, "unknown student")
    return await run(body.who, body.text.strip(), Path(tempfile.mkdtemp(prefix="tagout-")))
