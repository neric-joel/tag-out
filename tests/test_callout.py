"""Same-day call-out: "I'm sick, tag me out of Monday" opens a round now, and the reason never leaves the mascot."""

import pytest

from scripts.inproc import System


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


def shift_on(system, sid, weekday):
    return next(s for s in system.store(sid).shifts() if s.start.weekday() == weekday)


async def intake(system, sid, text):
    return await system.net.post(f"{system.reg['agents'][sid]}/intake", {"text": text})


async def test_callout_after_the_week_opens_its_own_round(system):
    week = await system.sunday_and_run()
    marco_notes = sum("No trade worked" in m["text"] for m in system.phone("marco"))
    assert marco_notes == 1
    monday = shift_on(system, "ben", 0)
    n = len(system.bus.history)

    r = await intake(system, "ben", "I woke up sick, can't make it Monday")
    assert r["engine"] == "callout" and "Mon 10 AM-2 PM" in r["reply"]
    assert "still on the schedule" in r["reply"], "never let a student think they're already excused"
    summary = await system.wait_for("summary", after=n)

    assert summary["kind"] == "callout" and summary["asked"] == 1 and summary["fixed"] == 1
    assert monday.id not in {s.id for s in system.store("ben").shifts()}
    takers = [a for a in system.apps if monday.id in {s.id for s in system.store(a).shifts()}]
    assert len(takers) == 1 and takers[0] != "ben"
    assert system.engine.summary == week, "the Sunday numbers stay the Sunday numbers"
    assert sum("No trade worked" in m["text"] for m in system.phone("marco")) == 1, "no repeat 'no trade' text"
    request = next(e for e in system.bus.history[n:] if e["type"] == "trade_request")
    assert request["urgent"] is True
    assert "sick" not in system.tap.dump().lower(), "the reason stays inside Ben's mascot"
    manager = [m["text"] for m in system.steward.state.s["phone"]]
    assert any(t.startswith("Same-day request: Ben can't work Mon 10 AM-2 PM") for t in manager)
    assert not any("sick" in t.lower() for t in manager)


async def test_callout_without_a_day_asks_which_shift(system):
    r = await intake(system, "ben", "I'm sick, tag me out")
    assert "Which shift" in r["reply"]
    ask = [m for m in system.phone("ben") if m["kind"] == "ask"][-1]
    assert [b["data"][:4] for b in ask["buttons"]] == ["out:", "out:"]
    n = len(system.bus.history)
    tapped = await system.net.post(f"{system.reg['agents']['ben']}/tap", {"data": ask["buttons"][0]["data"]})
    assert tapped["reply"].startswith("Asking your coworkers to cover")
    request = await system.wait_for("trade_request", after=n)
    assert request["shift_id"] == ask["buttons"][0]["data"][4:] and request["urgent"] is True


@pytest.mark.parametrize("text,is_callout", [
    ("I woke up sick, can't make it Monday", True),
    ("I am sick, cannot make it Sunday", True),
    ("can someone take my thursday shift, family emergency", True),
    ("im not feeling well, skip my shift", True),
    ("won't make it in tomorrow", True),
    ("dentist Thu 3pm", False),
    ("I feel well today, more hours please", False),
    ("I got the Amazon interview Thu 3pm!!", False),
])
def test_callout_phrases(text, is_callout):
    from datetime import date

    from ingest.text import callout
    assert (callout(text, date(2026, 10, 26), date(2026, 10, 25)) is not None) == is_callout
