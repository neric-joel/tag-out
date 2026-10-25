"""Work life beyond trades: extra shifts, team meetings, meetings with the supervisor, issue reports, and the
agent graph's wire events (with a nosy broker that gets nothing)."""

import asyncio

import pytest

from scripts.inproc import System


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


async def text(system, sid, words):
    return await system.net.post(f"{system.reg['agents'][sid]}/intake", {"text": words})


async def until(cond, timeout=15.0):
    async def poll():
        while not cond():
            await asyncio.sleep(0.05)
    await asyncio.wait_for(poll(), timeout)


def manager(system):
    return [m["text"] for m in system.steward.state.s["phone"]]


async def test_an_extra_shift_goes_to_someone_who_wants_hours_and_fits(system):
    await system.sunday_and_run()
    n = len(system.bus.history)
    r = await system.post("/manager/extra", {"date": "2026-10-29", "start": 18, "end": 22})
    summary = await system.wait_for("summary", after=n)
    assert summary["kind"] == "extra" and summary["fixed"] == 1
    taker = summary["taker"]
    assert r["shift_id"] in {s.id for s in system.store(taker).shifts()}
    assert system.store(taker).student().prefs.wants_more_hours, "only students who want hours pick it"
    assert taker not in ("ben", "dev"), "Ben (F-1 at 17 of 20) and Dev (25 h average) pass in private"
    assert any(t.startswith("Extra shift:") for t in manager(system))
    confirm = next(m for m in system.phone(taker) if m["kind"] == "confirm" and "extra shift" in m["text"])
    assert "Pay this week: +$64." in confirm["text"]


async def test_team_meeting_uses_busy_bits_only_and_counts_rsvps(system):
    r = await system.post("/manager/meeting", {})
    assert len(r["options"]) == 3 and r["options"][0]["free"] >= r["options"][-1]["free"]
    await until(lambda: any("coming" in t for t in manager(system)))
    invite = next(m for m in system.phone("ana") if "team meeting" in m["text"])
    assert "Only your answer goes back" in invite["text"]
    assert any(b.label == "Library team meeting" for b in system.store("ana").busy())


async def test_meeting_with_the_supervisor_sends_free_times_not_the_calendar(system):
    r = await text(system, "ana", "can I set up a meeting with my supervisor?")
    assert r["engine"] == "meeting"
    await until(lambda: any("booked a 30-minute meeting" in t for t in manager(system)))
    assert any(b.label == "Meeting with your supervisor" for b in system.store("ana").busy())
    req = next(f for f in system.tap.frames if f["url"].endswith("/meeting/request") and f["dir"] == "req")
    assert "CSE 310" not in req["body"] and "gym" not in req["body"].lower(), "only free times leave the mascot"


async def test_issue_report_goes_to_the_manager_after_the_student_says_so(system):
    r = await text(system, "ana", "the printer at the desk is broken again")
    assert r["engine"] == "issue"
    draft = next(m for m in system.phone("ana") if m["kind"] == "ask" and "printer" in m["text"])
    assert [b["label"] for b in draft["buttons"]] == ["Send with my name", "Send anonymously", "Don't send"]
    await until(lambda: any("Your manager saw your report" in m["text"] for m in system.phone("ana")))
    card = next(t for t in manager(system) if t.startswith("Issue reported (equipment)"))
    assert "From: Ana." in card


async def test_wire_events_show_what_crossed_and_hide_ballots(system):
    await system.sunday_and_run()
    wires = [e for e in system.bus.history if e["type"] == "wire"]
    schemas = {w["schema"] for w in wires}
    assert {"SundayCheck", "TradeRequest", "PickRequest", "RingCheck", "Prepare", "Vote", "Decision"} <= schemas
    prep = next(w for w in wires if w["schema"] == "Prepare")
    assert prep["payload"]["ballot"] == "•••" and prep["from"] == "broker"
    vote = next(w for w in wires if w["schema"] == "Vote")
    assert vote["payload"]["ballot"] == "•••" and vote["to"] == "broker"


async def test_a_nosy_broker_learns_nothing(system):
    await system.post("/demo/sunday")
    out = await system.post("/demo/snoop")
    assert all(v["why"] == 422 for v in out.values()), "a request with an undeclared field is rejected"
    assert all(v["room_probe"] is False for v in out.values()), "no mascot vouches for a shift it never picked"
