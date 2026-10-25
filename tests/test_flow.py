"""End-to-end: Sunday check -> TTC rounds -> ring + cover -> two-phase commit, and the freshness abort."""

import pytest

from scripts.inproc import System


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


def shift_ids(system, sid):
    return {s.id for s in system.store(sid).shifts()}


async def test_sunday_check_texts_only_on_collisions(system):
    await system.post("/demo/sunday")
    kinds = {sid: [m["kind"] for m in system.phone(sid)] for sid in system.apps}
    assert kinds["priya"] == []  # no collision, no text
    for sid in ("ana", "ben", "dev", "zoe", "marco"):
        assert "collision" in kinds[sid]
    ana = next(m for m in system.phone("ana") if m["kind"] == "collision")
    assert "Tue 6-10 PM" in ana["text"] and "CSE 310" in ana["text"] and "Canvas" in ana["text"]


async def test_week_ring_cover_and_honest_open_shift(system):
    summary = await system.sunday_and_run()
    assert summary["asked"] == 5
    assert summary["fixed"] == 4 and summary["open"] == 1
    assert summary["by_ring"] == 3 and summary["by_chain"] == 1
    assert summary["pay_kept"] == 192
    assert summary["open_shifts"] == ["library-wed-1028-1400-d2"]

    # the hero ring: Ana's Tue -> Ben, Ben's Thu -> Dev, Dev's Fri -> Ana
    assert "library-fri-1030-1000-d1" in shift_ids(system, "ana")
    assert "library-tue-1027-1800-d1" in shift_ids(system, "ben")
    assert "library-thu-1029-1400-d1" in shift_ids(system, "dev")
    assert "library-sat-1031-1000-d2" in shift_ids(system, "priya")

    types = [e["type"] for e in system.bus.history]
    assert "counter_window" in types, "round 1 found no cycle; the counter-offer round closed it"
    ask = [m for m in system.phone("ana") if m["kind"] == "ask"]
    assert ask and "gym" in ask[0]["text"]
    picks = [e["picks"] for e in system.bus.history if e["type"] == "picks" and e["phase"] == "swap"]
    ana = [pk["ana"] for pk in picks if "ana" in pk]
    assert ana[0] is None and ana[-1] == "library-fri-1030-1000-d1", "passed first, counter-offered after asking"
    window = next(i for i, e in enumerate(system.bus.history) if e["type"] == "counter_window")
    cycle = next(i for i, e in enumerate(system.bus.history) if e["type"] == "cycle")
    assert window < cycle

    ben = next(m for m in system.phone("ben") if m["kind"] == "confirm")
    assert "17 of your 20 hours" in ben["text"]


async def test_editing_a_week_before_commit_aborts_and_retries(system):
    await system.post("/admin/auto", {"enabled": False, "agents": ["dev"], "delay": 0.05})
    await system.post("/demo/sunday")
    await system.post("/phone/dev/tap", {"data": "trade:yes:library-fri-1030-1000-d1"})
    await system.settle(0.3)
    await system.post("/demo/run")
    prep = await system.wait_for("prepare")
    assert set(prep["members"]) == {"ana", "ben", "dev"}
    await system.post("/demo/break")
    abort = await system.wait_for("abort")
    assert abort["proposal"] == prep["proposal"]
    stale = [e for e in system.bus.history if e["type"] == "vote" and e["vote"] == "stale"]
    assert stale and stale[0]["agent"] == "dev"
    # nothing moved: everyone still has their original shifts at the moment of abort
    assert "library-tue-1027-1800-d1" not in shift_ids(system, "ben") or system.engine.committed
    await system.post("/admin/auto", {"enabled": True, "agents": ["dev"], "delay": 0.05})
    summary = await system.wait_for("summary", timeout=30)
    assert summary["fixed"] == 4
    # the next proposal is a chain anchored by Priya's cover: Priya <- Ben's Thu, Ben <- Ana's Tue, Ana <- Dev's Fri
    assert "library-thu-1029-1400-d1" in shift_ids(system, "priya")
    assert "library-tue-1027-1800-d1" in shift_ids(system, "ben")
    assert "library-fri-1030-1000-d1" in shift_ids(system, "ana")
    assert "library-fri-1030-1000-d1" not in shift_ids(system, "dev")
