"""What judges hit on the live system: swap requests by text, texts with nothing in them, a backwards extra shift,
and trade rounds started before the Sunday taps landed."""

import httpx
import pytest

from scripts.inproc import System


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


async def intake(system, sid, text):
    return await system.net.post(f"{system.reg['agents'][sid]}/intake", {"text": text})


def test_a_swap_request_routes_as_a_trade_with_its_day():
    from datetime import date

    from ingest import text

    r, how = text.route("can i swap my sat shift?", date(2026, 10, 26))
    assert (r["intent"], r["weekday"], how) == ("trade", 5, "regex")
    assert text.route("dentist Thu 3pm", date(2026, 10, 26))[0]["intent"] == "calendar"


async def test_asking_to_swap_offers_find_a_trade_for_that_shift(system):
    r = await intake(system, "ben", "can i swap my thursday shift?")
    assert r["engine"] == "trade"
    ask = next(m for m in reversed(system.phone("ben")) if m["buttons"])
    thursday = next(s for s in system.store("ben").shifts() if s.start.weekday() == 3)
    assert ask["buttons"][0]["data"] == f"trade:yes:{thursday.id}"
    assert "why" in ask["text"]


async def test_a_text_with_nothing_in_it_says_so(system):
    r = await intake(system, "ana", "hmm ok")
    assert "nothing changed" in r["reply"] and "Noted" not in r["reply"]


async def test_a_backwards_extra_shift_is_refused(system):
    with pytest.raises(httpx.HTTPStatusError) as e:
        await system.net.post(f"{system.reg['steward']}/manager/extra", {"date": "2026-10-26", "start": 20, "end": 8})
    assert e.value.response.status_code == 400
    assert not system.steward.state.s["extras"]


async def test_rounds_started_right_after_sunday_wait_for_the_taps(system):
    await system.post("/demo/sunday")
    await system.post("/demo/run")  # at once, before anyone has tapped "Find a trade"
    week = await system.wait_for("summary", timeout=60)
    assert week["asked"] == 5 and week["fixed"] == 4
