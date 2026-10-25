"""The campus hierarchy (org/app.py): a case climbs one rung each time a timer runs out, silence never approves,
safety skips the ladder, F-1 questions go to ISSC only when the student says so, and no reason ever climbs."""

import asyncio
import json

import pytest

from scripts.inproc import System
from seeds.org import ROLES, members


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path, org_minute=0.002)  # two story hours take a quarter of a second
    yield s
    await s.close()


async def text(system, sid, words):
    return await system.net.post(f"{system.reg['org'][sid]}/intake", {"text": words})


async def until(system, pred, timeout=15.0, after=0):
    async def poll():
        while True:
            hit = next((e for e in system.bus.history[after:] if pred(e)), None)
            if hit:
                return hit
            await asyncio.sleep(0.02)
    return await asyncio.wait_for(poll(), timeout)


def org_events(system, after=0):
    return [e for e in system.bus.history[after:] if e["type"].startswith("org_")]


async def test_uncovered_callout_climbs_two_rungs_then_the_backup_finds_a_cover(system):
    shift = next(s for s in system.store("lena").shifts() if s.start.weekday() == 5)
    r = await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    assert r["engine"] == "callout"
    done = await until(system, lambda e: e["type"] == "org_done")
    evs = org_events(system)

    climbs = [(e["frm"], e["to"], e["rule"]) for e in evs if e["type"] == "org_escalate"]
    assert climbs == [("nia", "dining_mgr", "no_cover_2h"), ("dining_mgr", "backup", "no_answer_30m")]
    assert done["outcome"] == "covered" and done["taker"] == "omar" and done["by"] == "backup"

    # the shift lead asked every Dining coworker twice (Ben and Raj work there too); all of them passed
    lead = [e for e in evs if e["type"] == "org_picks" and e["by"] == "nia"]
    assert len(lead) == 2 and set(lead[0]["picks"]) == set(members("dining")) - {"lena"}
    assert all(v is None for e in lead for v in e["picks"].values())
    # Raj passed for a reason only his mascot knows (Rec plus Dining hours would break his F-1 20); his own
    # rulebook says so, while the wire only ever carried a pass
    from agents.brain import to_shift
    from rulebook.rules import check_change
    raj = system.store("raj")
    ref = system.org["nia"].state.s["roster"][shift.id]
    assert not check_change(raj.student(), raj.shifts(), add=[to_shift(ref)], drop=[], busy=raj.busy()).ok

    assert shift.id in {s.id for s in system.store("omar").shifts()}
    assert shift.id not in {s.id for s in system.store("lena").shifts()}
    wire = json.dumps([e for e in system.bus.history if e["type"] == "wire"]).lower()
    assert "sick" not in wire, "the reason stays in Lena's mascot"


async def test_silence_never_approves(system):
    """With nobody answering anywhere, the case reaches the top and stays open; nothing moves."""
    for r in ROLES:
        if r in system.org:
            await system.net.post(f"{system.reg['org'][r]}/admin/auto", {"enabled": False})
    shift = next(s for s in system.store("lena").shifts() if s.start.weekday() == 5)
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_overdue")
    climbs = [e["to"] for e in org_events(system) if e["type"] == "org_escalate"]
    assert climbs == ["dining_mgr", "backup", "hr"]
    assert not any(e["type"] == "org_done" for e in org_events(system))
    assert shift.id in {s.id for s in system.store("lena").shifts()}, "a timeout never moves a shift"


async def test_safety_report_skips_the_ladder(system):
    await text(system, "tess", "The fire exit by the weight room is blocked with boxes again, it's unsafe")
    done = await until(system, lambda e: e["type"] == "org_done")
    climbs = [(e["frm"], e["to"], e["rule"]) for e in org_events(system) if e["type"] == "org_escalate"]
    assert climbs == [("rec_mgr", "hr", "safety_first")], "straight to Student Employment, no shift lead"
    assert done["by"] == "hr" and done["outcome"] == "acknowledged"
    await asyncio.sleep(0.2)
    assert any("saw your report" in m["text"] for m in system.phone("tess"))


async def test_f1_question_goes_to_issc_only_after_the_student_says_send(system):
    await system.net.post(f"{system.reg['org']['kofi']}/admin/auto", {"enabled": False})
    r = await text(system, "kofi", "Can I work 40 hours over winter break on my F-1 if I graduate in December?")
    assert r["engine"] == "visa"
    await asyncio.sleep(0.2)
    assert not any(e["type"] == "org_case" for e in org_events(system)), "nothing leaves before the student taps"
    ask = next(m for m in reversed(system.phone("kofi")) if m["buttons"])
    assert [b["label"] for b in ask["buttons"]] == ["Send to ISSC", "Don't send"]
    await system.net.post(f"{system.reg['org']['kofi']}/tap", {"data": ask["buttons"][0]["data"]})
    done = await until(system, lambda e: e["type"] == "org_done")
    assert done["by"] == "issc" and done["outcome"] == "answered"
    await asyncio.sleep(0.2)
    reply = system.phone("kofi")[-1]["text"]
    assert "ISSC" in reply and "Not legal or immigration advice" in reply
    sent = [e for e in system.bus.history if e["type"] == "wire" and e["path"] == "/question"]
    assert len(sent) == 1 and set(sent[0]["payload"]) == {"question_id", "agent_id", "text"}
