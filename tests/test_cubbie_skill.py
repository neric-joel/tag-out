"""The Cubbie Skill: sample mode works offline, and its import path lands calendar items in the mascot privately."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

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
