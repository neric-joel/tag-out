"""What a Library-only scheduler would do with the same week, and the manager's export after Tag Out's trades."""

import csv
import io

import pytest

from scripts.inproc import System


@pytest.fixture
async def system(tmp_path):
    s = System(tmp=tmp_path)
    yield s
    await s.close()


async def test_a_library_only_scheduler_breaks_limits_it_cannot_see(system):
    await system.post("/demo/sunday")
    await system.settle(0.4)
    r = await system.net.client.get(f"{system.reg['broker']}/admin/baseline")
    rows = {row["shift_id"]: row for row in r.json()["rows"]}
    ana_tue = rows["library-tue-1027-1800-d1"]
    assert ana_tue["to"] == "ben"
    assert ana_tue["library_view"] == 12 and ana_tue["real"] == 21  # the Library sees 12 h; Ben is really at 21
    assert "f1_weekly_20" in ana_tue["breaks"]
    ben_thu = rows["library-thu-1029-1400-d1"]
    assert ben_thu["to"] == "dev" and "aca_25_avg" in ben_thu["breaks"]  # Dev's rec center hours are invisible too
    assert r.json()["violations"] >= 2


async def test_manager_export_marks_traded_shifts(system):
    await system.sunday_and_run()
    r = await system.net.client.get(f"{system.reg['broker']}/roster.csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    changed = {row["shift_id"]: row["worker"] for row in rows if row["changed_by_trade"] == "yes"}
    assert changed["library-tue-1027-1800-d1"] == "Ben"
    assert changed["library-fri-1030-1000-d1"] == "Ana"
    ics = await system.net.client.get(f"{system.reg['broker']}/roster.ics")
    assert b"Changed by an approved Tag Out trade" in ics.content


async def test_baseline_describes_the_week_before_any_trade(system):
    await system.post("/demo/sunday")
    await system.settle(0.4)
    await system.post("/demo/run")
    await system.wait_for("summary", timeout=30)
    r = await system.net.client.get(f"{system.reg['broker']}/admin/baseline")
    rows = {row["shift_id"]: row for row in r.json()["rows"]}
    assert rows["library-tue-1027-1800-d1"]["to"] == "ben"  # still the pre-trade week, not the fixed roster
    assert "f1_weekly_20" in rows["library-tue-1027-1800-d1"]["breaks"]
