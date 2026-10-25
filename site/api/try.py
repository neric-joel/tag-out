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
os.environ.setdefault("TAGOUT_OFFLINE", "1")  # no API key on the server: texts go to the regex parser or the cache
os.environ.setdefault("TAGOUT_RUNTIME", str(Path(tempfile.gettempdir()) / "tagout-runtime"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

app = FastAPI()


class Try(BaseModel):
    who: str
    text: str = Field(min_length=1, max_length=240)


@app.post("/api/try")
async def try_message(body: Try) -> dict:
    from scripts.record import PEOPLE
    from scripts.record import try_message as run

    if body.who not in PEOPLE:
        raise HTTPException(400, "unknown student")
    return await run(body.who, body.text.strip(), Path(tempfile.mkdtemp(prefix="tagout-")))
