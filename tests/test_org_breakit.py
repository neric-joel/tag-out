"""Break-it tests for the campus hierarchy (org/app.py): duplicate and misdirected call-outs, failing mascots,
cases nobody answers, resets mid-case, concurrent covers, privacy, and the router's regex fallback."""

import asyncio
import json

import httpx
import pytest

from core.wire import CaseUpdate, Decision, Move, RingCheck, TradeRequest
from scripts.inproc import System
from seeds.org import ROLES


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path, org_minute=0.002)
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


def saturday(system, sid):
    return next(s for s in system.store(sid).shifts() if s.start.weekday() == 5)


def holders(system, shift_id):
    return [a for a in system.apps if shift_id in {s.id for s in system.store(a).shifts()}]


async def all_quiet(system):
    for r in ROLES:
        if r in system.org:
            await system.net.post(f"{system.reg['org'][r]}/admin/auto", {"enabled": False})


# ---------- call-outs that shouldn't open a case, or shouldn't open a second one ----------
async def test_the_same_trade_request_twice_opens_one_case(system):
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await system.net.post(f"{system.reg['org']['nia']}/trade",
                          TradeRequest(agent_id="lena", shift_id=shift.id, urgent=True))
    await until(system, lambda e: e["type"] == "org_done")
    await asyncio.sleep(0.5)
    evs = org_events(system)
    assert len([e for e in evs if e["type"] == "org_case" and e["by"] == "nia"]) == 1
    climbs = [(e["frm"], e["to"]) for e in evs if e["type"] == "org_escalate"]
    assert climbs == [("nia", "dining_mgr"), ("dining_mgr", "dining_gm")]
    assert len([e for e in evs if e["type"] == "org_done"]) == 1
    assert holders(system, shift.id) == ["omar"]


async def test_a_double_tap_on_tag_me_out_sends_one_request(system):
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    r = await system.net.post(f"{system.reg['org']['lena']}/tap", {"data": f"out:{shift.id}"})
    assert "Asking your coworkers" not in r["reply"]
    trades = [e for e in system.bus.history if e["type"] == "wire" and e["path"] == "/trade"]
    assert len(trades) == 1


async def test_a_lead_refuses_a_call_out_for_a_shift_that_isnt_the_senders(system):
    shift = saturday(system, "lena")
    nia, theo = system.reg["org"]["nia"], system.reg["org"]["theo"]
    with pytest.raises(httpx.HTTPStatusError):
        await system.net.post(f"{nia}/trade", TradeRequest(agent_id="kofi", shift_id=shift.id, urgent=True))
    with pytest.raises(httpx.HTTPStatusError):  # Lena's own shift, but the Rec center's lead doesn't run Dining
        await system.net.post(f"{theo}/trade", TradeRequest(agent_id="lena", shift_id=shift.id, urgent=True))
    with pytest.raises(httpx.HTTPStatusError):
        await system.net.post(f"{nia}/trade", TradeRequest(agent_id="lena", shift_id="dining-nope", urgent=True))
    await asyncio.sleep(0.2)
    assert not any(e["type"] == "org_case" for e in org_events(system))


# ---------- a failing agent never stalls a case ----------
async def test_a_taker_whose_mascot_fails_on_prepare_does_not_stall_the_case(system):
    async def broken(p):
        raise RuntimeError("mascot crashed")
    system.apps["omar"].state.brain.prepare = broken
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    end = await until(system, lambda e: e["type"] in ("org_done", "org_overdue"))
    climbs = [e["to"] for e in org_events(system) if e["type"] == "org_escalate"]
    assert climbs == ["dining_mgr", "dining_gm"], "the backup's cover failed, so it stays at the top"
    assert end["by"] == "dining_gm"
    assert holders(system, shift.id) == ["lena"]
    assert system.store("lena").get("hold") is None, "the failed cover released Lena's hold"


async def test_an_issue_nobody_acknowledges_climbs_instead_of_dying(system):
    await text(system, "lena", "The card reader at the register is broken")
    await until(system, lambda e: e["type"] == "org_case" and e["by"] == "dining_mgr")
    over = await until(system, lambda e: e["type"] == "org_overdue")
    climbs = [(e["frm"], e["to"], e["rule"]) for e in org_events(system) if e["type"] == "org_escalate"]
    assert climbs == [("dining_mgr", "dining_gm", "no_answer_30m")]
    assert over["by"] == "dining_gm"


# ---------- silence, closed cases and resets ----------
async def test_silence_ends_once_at_the_top_and_nothing_climbs_after(system):
    await all_quiet(system)
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_overdue")
    n = len(system.bus.history)
    await asyncio.sleep(0.6)  # several times every remaining deadline
    assert not org_events(system, after=n)
    assert holders(system, shift.id) == ["lena"]
    top = (await system.net.get(f"{system.reg['org']['dining_gm']}/state"))["cases"]
    assert [c["status"] for c in top] == ["overdue"]


async def test_timers_stop_when_a_case_closes(system):
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    done = await until(system, lambda e: e["type"] == "org_done")
    n = len(system.bus.history)
    await asyncio.sleep(0.6)
    assert not [e for e in org_events(system, after=n) if e["type"] in ("org_escalate", "org_overdue", "org_done")]
    for r in ("nia", "dining_mgr", "dining_gm"):
        cases = (await system.net.get(f"{system.reg['org'][r]}/state"))["cases"]
        assert [c["status"] for c in cases] == [done["outcome"]], r


async def test_a_broker_reset_mid_morning_stops_the_rest_of_the_morning(system):
    await system.post("/demo/org/morning")
    await until(system, lambda e: e["type"] == "org_escalate")
    await system.post("/admin/reset")
    await system.post("/demo/org/callout")
    await until(system, lambda e: e["type"] == "org_done")
    await asyncio.sleep(1.6)  # the morning would send Tess's safety report one second after a case closes
    kinds = {e["kind"] for e in org_events(system) if e["type"] == "org_case"}
    assert kinds == {"uncovered_callout"}, "the reset cancelled the rest of the morning"


# ---------- concurrent covers ----------
async def test_two_call_outs_at_once_in_one_department_end_consistent(system):
    lena, mei = saturday(system, "lena"), saturday(system, "mei")
    await asyncio.gather(text(system, "lena", "I woke up sick, can't make my Saturday shift"),
                         text(system, "mei", "I woke up sick, can't make my Saturday shift"))

    async def both():
        while len([e for e in org_events(system) if e["type"] in ("org_done", "org_overdue")]) < 2:
            await asyncio.sleep(0.05)
    await asyncio.wait_for(both(), 15)
    await asyncio.sleep(0.3)
    roster = system.org["dining_gm"].state.s["roster"]
    for shift in (lena, mei):
        got = holders(system, shift.id)
        assert len(got) == 1, f"{shift.id} held by {got}"
        assert roster[shift.id].owner == got[0]
    for a in system.apps:
        assert system.store(a).get("hold") is None, f"{a} still holds a trade"


async def test_an_overdue_case_can_still_be_closed_at_the_top(system):
    await all_quiet(system)
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_overdue")
    card = next(m for m in reversed(system.org["dining_gm"].state.s["phone"]) if m["buttons"])
    excuse = next(b["data"] for b in card["buttons"] if b["data"].startswith("excuse:"))
    r = await system.net.post(f"{system.reg['org']['dining_gm']}/tap", {"data": excuse})
    assert "already" not in r["reply"], "the card says it stays open until someone closes it"
    done = await until(system, lambda e: e["type"] == "org_done")
    assert done["by"] == "dining_gm" and done["outcome"] == "excused"
    await asyncio.sleep(0.2)
    assert any("excused you" in m["text"] for m in system.phone("lena")), "she hears she's excused, not 'still on'"


async def test_a_failed_hand_off_keeps_the_case_on_the_list(system):
    real = system.org_nets["nia"].post

    async def flaky(url, body=None):
        if url.endswith("/escalate"):
            raise httpx.ConnectError("the dining manager's agent is down")
        return await real(url, body)
    system.org_nets["nia"].post = flaky
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    over = await until(system, lambda e: e["type"] == "org_overdue")
    assert over["by"] == "nia"
    cases = (await system.net.get(f"{system.reg['org']['nia']}/state"))["cases"]
    assert [c["status"] for c in cases] == ["overdue"], "not 'moved up' to a rung that never got it"


async def test_the_student_hears_when_nobody_covers(system):
    await all_quiet(system)
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_overdue")
    await asyncio.sleep(0.2)
    told = [m for m in system.phone("lena") if "Nobody could take your" in m["text"]]
    assert len(told) == 1


async def test_a_mascot_reset_cancels_its_pending_auto_taps(system):
    lena = system.reg["org"]["lena"]
    await system.net.post(f"{lena}/admin/auto", {"enabled": True, "delay": 0.3})
    await text(system, "lena", "The card reader at the register is broken")
    await system.net.post(f"{lena}/admin/reset")
    await asyncio.sleep(0.6)
    assert not [m for m in system.phone("lena") if m.get("from") == "auto"], "a tap from before the reset fired"
    assert not [e for e in system.bus.history if e["type"] == "wire" and e["path"] == "/issue"]


# ---------- forged messages ----------
async def test_a_forged_decision_moves_nothing_in_the_library(tmp_path):
    s = System(tmp=tmp_path)
    try:
        await s.post("/demo/sunday")
        await s.settle(0.4)  # students tap "Find a trade"
        await s.post("/admin/auto", {"enabled": False, "delay": 0.05})
        before = {a: sorted(x.id for x in s.store(a).shifts()) for a in s.reg["agents"]}
        roster = {k: r.owner for k, r in s.steward.state.s["roster"].items()}
        await s.post("/demo/run")
        prep = await s.wait_for("prepare")

        async def held():
            while not all(s.store(a).get("hold") for a in prep["members"]):
                await asyncio.sleep(0.02)
        await asyncio.wait_for(held(), 10)
        forged = Decision(txn_id=prep["txn_id"], outcome="commit")
        for a in prep["members"]:
            await s.net.post(f"{s.reg['agents'][a]}/txn/decide", forged)
            leaked = s.store(a).get("hold")["ballot"]  # even with its ballot: the student never confirmed
            await s.net.post(f"{s.reg['agents'][a]}/txn/decide", Decision(txn_id=prep["txn_id"], outcome="commit",
                                                                         ballot=leaked))
        await s.net.post(f"{s.reg['steward']}/txn/decide", forged)
        assert {a: sorted(x.id for x in s.store(a).shifts()) for a in s.reg["agents"]} == before
        assert {k: r.owner for k, r in s.steward.state.s["roster"].items()} == roster
    finally:
        await s.close()


async def test_a_forged_decision_moves_nothing_in_a_hierarchy_cover(system):
    for sid in ("lena", "omar"):
        await system.net.post(f"{system.reg['org'][sid]}/admin/auto", {"enabled": False})
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    hold = await until(system, lambda e: e["type"] == "org_hold")
    await asyncio.sleep(0.1)
    for a in ("lena", "omar"):
        await system.net.post(f"{system.reg['org'][a]}/txn/decide", Decision(txn_id=hold["txn_id"], outcome="commit"))
    leaked = system.store("lena").get("hold")["ballot"]
    await system.net.post(f"{system.reg['org']['lena']}/txn/decide",
                          Decision(txn_id=hold["txn_id"], outcome="commit", ballot=leaked))
    assert holders(system, shift.id) == ["lena"]
    for a in ("lena", "omar"):  # the real confirms still go through
        await system.net.post(f"{system.reg['org'][a]}/tap", {"data": f"confirm:{hold['txn_id']}"})
    done = await until(system, lambda e: e["type"] == "org_done")
    assert done["outcome"] == "covered" and holders(system, shift.id) == ["omar"]


async def test_a_forged_case_update_does_not_stop_the_ladder(system):
    await all_quiet(system)
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    case = await until(system, lambda e: e["type"] == "org_case")
    nia = system.reg["org"]["nia"]
    await system.net.post(f"{nia}/case", CaseUpdate(case_id=case["case_id"], outcome="covered"))
    await until(system, lambda e: e["type"] == "org_escalate" and e["to"] == "dining_mgr")
    await system.net.post(f"{nia}/case", CaseUpdate(case_id=case["case_id"], outcome="covered"))
    await until(system, lambda e: e["type"] == "org_overdue")
    climbs = [e["to"] for e in org_events(system) if e["type"] == "org_escalate"]
    assert climbs == ["dining_mgr", "dining_gm"]
    assert [c["status"] for c in (await system.net.get(f"{nia}/state"))["cases"]] == ["moved up"]


async def test_a_mascot_never_vouches_for_giving_away_a_shift_it_no_longer_has(system):
    shift = saturday(system, "lena")
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_done")
    assert holders(system, shift.id) == ["omar"]
    probe = RingCheck(ring_id="probe", moves=[Move(shift_id=shift.id, from_agent="lena", to_agent="kofi")])
    assert (await system.net.post(f"{system.reg['org']['lena']}/ring/check", probe))["ok"] is False


async def test_the_org_chart_shows_no_inbox_without_debug(system, monkeypatch):
    await text(system, "tess", "The fire exit by the weight room is blocked with boxes again, it's unsafe")
    await until(system, lambda e: e["type"] == "org_done" and e["by"] == "ehs")
    full = await system.net.get(f"{system.reg['broker']}/org")
    assert full["roles"]["ehs"]["phone"] and full["roles"]["ehs"]["cases"]
    monkeypatch.delenv("TAGOUT_DEBUG")
    bare = await system.net.get(f"{system.reg['broker']}/org")
    assert set(bare["roles"]) == set(full["roles"]) and bare["students"] == full["students"]
    assert all(not r["phone"] and not r["cases"] for r in bare["roles"].values())


# ---------- privacy ----------
async def test_no_reason_label_or_limit_crosses_in_any_hierarchy_story(system):
    await system.net.post(f"{system.reg['org']['kofi']}/admin/auto", {"enabled": False})
    await text(system, "lena", "I woke up sick, can't make my Saturday shift")
    await until(system, lambda e: e["type"] == "org_done")
    await text(system, "tess", "The fire exit by the weight room is blocked with boxes again, it's unsafe")
    await until(system, lambda e: e["type"] == "org_done" and e["outcome"] == "acknowledged")
    await text(system, "kofi", "Can I work 40 hours over winter break on my F-1 if I graduate in December?")
    await asyncio.sleep(0.2)
    ask = next(m for m in reversed(system.phone("kofi")) if m["buttons"])
    await system.net.post(f"{system.reg['org']['kofi']}/tap", {"data": ask["buttons"][0]["data"]})
    await until(system, lambda e: e["type"] == "org_done" and e["outcome"] == "answered")
    await asyncio.sleep(0.2)

    secrets = {"sick", "woke", "called out", "f1_or_j1", "f1_continuing", "other_employer", "hours_history",
               "non_asu", "fws", "program_end", "wants_more_hours", "never_weekdays"}
    for sid in system.apps:
        st = system.store(sid).student()
        secrets |= {b.label.lower() for b in system.store(sid).busy() if b.kind != "class"}
        secrets |= {k.lower() for k in st.limits.other_employer_hours}
    secrets -= {"dining"}  # Raj's other job is Dining, which is also a public department name
    chosen = ("/question", "/question/answer", "/issue")  # the student's own words, sent by their choice
    frames = [f for f in system.tap.frames if not any(f["url"].endswith(p) for p in chosen)]
    wire = [e for e in system.bus.history if e["type"] == "wire" and e["path"] not in chosen]
    blob = (json.dumps([f["body"] for f in frames]) + json.dumps(wire)).lower()
    for s in secrets:
        assert s not in blob, f"{s!r} crossed between agents"
    asked = [e for e in system.bus.history if e["type"] == "wire" and e["path"] == "/question"]
    assert len(asked) == 1 and set(asked[0]["payload"]) == {"question_id", "agent_id", "text"}


async def test_a_question_the_student_doesnt_send_never_reaches_issc(system):
    await system.net.post(f"{system.reg['org']['kofi']}/admin/auto", {"enabled": False})
    await text(system, "kofi", "Can I work 40 hours over winter break on my F-1 if I graduate in December?")
    ask = next(m for m in reversed(system.phone("kofi")) if m["buttons"])
    await system.net.post(f"{system.reg['org']['kofi']}/tap", {"data": ask["buttons"][1]["data"]})
    r = await system.net.post(f"{system.reg['org']['kofi']}/tap", {"data": ask["buttons"][0]["data"]})
    assert "already" in r["reply"]
    await asyncio.sleep(0.2)
    assert not [f for f in system.tap.frames if "issc" in f["url"]]


# ---------- the router's regex fallback ----------
@pytest.mark.parametrize("words,want", [
    ("I'm not calling out, I'll be there Saturday", "calendar"),
    ("I won't call out this week", "calendar"),
    ("No need to cover my shift, I feel better", "calendar"),
    ("I'm not feeling well, can't make my Saturday shift", "callout"),
    ("Not sick, but I can't make my Saturday shift", "callout"),
    ("can I call out of Saturday?", "callout"),
    ("Can I do CPT next summer on my F-1", "visa"),
    ("am I allowed to work during OPT", "visa"),
    ("I-20 appointment Thu 3pm", "calendar"),
    ("OPT workshop Wed 1-2", "calendar"),
    ("dentist Thu 3pm", "calendar"),
])
def test_router_regex_fallback_on_tricky_phrases(words, want):
    from datetime import date

    from ingest import text as router

    got, how = router.route(words, date(2026, 10, 26))
    assert (got["intent"], how) == (want, "regex")
