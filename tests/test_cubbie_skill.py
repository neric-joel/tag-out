"""The Cubbie Skill: sample mode works offline, and its import path lands calendar items in the mascot privately."""

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn

from scripts.inproc import System

SKILL = Path(__file__).resolve().parent.parent / "cubbie-skill" / "tag-out"


def run(*args: str) -> str:
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "tagout.py"), "--sample", *args],
                          capture_output=True, text=True, timeout=30).stdout


def test_sample_mode_needs_no_network_or_account():
    out = run("inbox")
    assert "Find a trade" in out and "code: confirm:txn-3" in out
    assert "would send 2 canvas items" in run("sync", "--source", "canvas")
    assert run("answer", "confirm:txn-3").strip() == "Confirmed. Waiting for the others."


def test_skill_frontmatter_first_sentence_fits_cubbie_list():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    desc = next(line for line in text.splitlines() if line.startswith("description:"))[len("description: "):]
    assert len(desc.split(". ")[0]) <= 200 and len(desc) <= 1024


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


async def test_cubbie_import_becomes_private_busy_time(system):
    events = json.loads((SKILL / "assets" / "sample_calendar.json").read_text())
    r = await system.net.client.post("http://zoe.mascot/import", json={"source": "calendar", "events": events})
    assert r.json()["imported"] == 1
    labels = [b.label for b in system.store("zoe").busy()]
    assert "Gym with roommate" in labels
    v = await system.net.client.get("http://zoe.mascot/version")
    assert v.json()["version"] >= 2  # an import is a schedule change, so a held trade would go stale


async def test_cubbie_script_against_a_live_mascot(system, tmp_path, monkeypatch):
    """The real client path, not --sample: tagout.py over HTTP to a running mascot, owner token enforced."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(system.apps["zoe"], host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    await system.post("/admin/auto", {"enabled": False, "agents": ["zoe"]})  # Zoe answers through Cubbie
    monkeypatch.setenv("TAGOUT_DEBUG", "0")  # from here on the mascot checks the owner token for real
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "TAGOUT_OWNER_TOKEN": system.store("zoe").get("owner_token")}

    async def live(*args: str, token: str | None = None) -> str:
        e = env if token is None else {**env, "TAGOUT_OWNER_TOKEN": token}
        p = await asyncio.to_thread(subprocess.run, [sys.executable, str(SKILL / "scripts" / "tagout.py"), *args],
                                    capture_output=True, text=True, timeout=30, env=e)
        return p.stdout

    try:
        url = f"http://127.0.0.1:{port}"
        assert "set up" in await live("setup", "--mascot-url", url)
        events = str(SKILL / "assets" / "sample_calendar.json")
        assert "sent 1 calendar items" in await live("sync", "--source", "calendar", "--events", events)
        await system.post("/demo/sunday")
        inbox = await live("inbox")
        code = re.search(r"code: (trade:yes:\S+)", inbox).group(1)
        assert "Find a trade" in inbox
        assert (await live("answer", code)).startswith("Looking for a trade")
        assert code.split(":")[2] in system.engine.requests, "the tap reached the broker as a trade request"
        assert (await live("tell", "dentist Thu 3pm")).startswith("Noted")
        await live("setup", "--mascot-url", url, token="not-zoes-token")
        assert "refused the token" in await live("inbox")
    finally:
        server.should_exit = True
        await task
