"""End to end in a real browser, the way a judge uses the site. Opt in: TAGOUT_E2E=1 (CI runs the unit tests only).

    TAGOUT_E2E=1 python -m pytest tests/e2e -q                      # the hosted replay, served from site/
    TAGOUT_E2E=1 TAGOUT_E2E_URL=https://tag-out.vercel.app python -m pytest tests/e2e -q
    TAGOUT_E2E=1 TAGOUT_E2E_LIVE=1 python -m pytest tests/e2e -q    # also the live system (python -m scripts.run_all)
"""

from __future__ import annotations

import functools
import http.server
import os
import re
import threading
from pathlib import Path

import pytest

if os.environ.get("TAGOUT_E2E") != "1":
    pytest.skip("browser tests are opt-in: set TAGOUT_E2E=1", allow_module_level=True)

from playwright.sync_api import expect, sync_playwright  # noqa: E402

SITE = Path(__file__).resolve().parents[2] / "site"
CHANNEL = os.environ.get("TAGOUT_E2E_CHANNEL", "msedge")


@pytest.fixture(scope="module")
def base_url():
    if os.environ.get("TAGOUT_E2E_URL"):
        yield os.environ["TAGOUT_E2E_URL"].rstrip("/")
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(channel=CHANNEL)
        yield b
        b.close()


def ready(page):
    """The hosted page has loaded its recording and wired its buttons."""
    expect(page.locator("#liveText")).to_have_text("Recording", timeout=30_000)


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    ctx.close()


def test_play_the_week_on_the_hosted_page(page, base_url):
    page.goto(base_url + "/", wait_until="domcontentloaded")
    ready(page)
    expect(page.locator(".static-banner")).to_contain_text("recording of the real system")
    page.get_by_role("button", name="Play the week").first.click()
    expect(page.locator("#kFixed")).to_contain_text("4", timeout=60_000)
    expect(page.locator("#kFixed")).to_contain_text("of 5")
    expect(page.locator("#kPay")).to_have_text("$192")
    assert page.locator("#events tr").count() > 20
    expect(page.locator("#finding")).to_contain_text("3-way ring")
    assert page.errors == []


def test_sign_in_as_ben_shows_his_private_week(page, base_url):
    page.goto(base_url + "/", wait_until="domcontentloaded")
    ready(page)
    page.locator("#whoPill").click()
    page.locator("#people button[data-who='ben']").click()
    expect(page.locator("#viewStudent")).to_be_visible()
    expect(page.locator("#meTitle")).to_have_text("Ben's week")
    expect(page.locator("#meWeek")).to_contain_text("Amazon interview")
    expect(page.locator("#mePrivate")).to_contain_text("can't see")  # his Dining hours, which the Library can't see
    page.locator("#meChips button", has_text="sick").click()
    expect(page.locator("#meThread")).to_contain_text("still on the schedule", timeout=30_000)
    assert page.errors == []


def test_manager_page_shows_approvals_and_the_roster(page, base_url):
    page.goto(base_url + "/", wait_until="domcontentloaded")
    ready(page)
    page.get_by_role("button", name="Play the week").first.click()
    expect(page.locator("#kFixed")).to_contain_text("of 5", timeout=60_000)
    page.goto(base_url + "/#manager", wait_until="domcontentloaded")
    expect(page.locator("#viewManager")).to_be_visible()
    expect(page.locator("#mgrThread")).to_contain_text("standing rule", timeout=30_000)
    expect(page.locator("#mgrBoard")).to_contain_text("Marco")
    assert page.errors == []


def test_how_it_works_counts_messages_and_finds_no_leak(page, base_url):
    page.goto(base_url + "/#agents", wait_until="domcontentloaded")
    ready(page)
    page.locator("#agSunday").click()
    expect(page.locator("#lkMsgs")).to_have_text(re.compile(r"^[1-9]\d{2,}"), timeout=60_000)  # 100+ messages
    expect(page.locator("#lkFields")).to_have_text("0")
    expect(page.locator("#lkLabels")).to_have_text("0")
    page.locator(".tof-row").first.click()
    expect(page.locator(".tof-json:visible, .tof-owner-text:visible").first).not_to_be_empty()
    expect(page.locator("#ledger")).to_contain_text("tests/test_baseline.py")
    assert page.errors == []


def test_org_chart_plays_the_morning_up_the_ladder(page, base_url):
    page.goto(base_url + "/#org", wait_until="domcontentloaded")
    ready(page)
    expect(page.locator(".org-node")).to_have_count(27, timeout=30_000)  # 16 students, 3 leads, 8 people above
    page.get_by_role("button", name="Play the morning").click()
    case = page.locator(".org-case").last
    expect(case).to_contain_text("up to Dining manager", timeout=30_000)
    expect(case).to_contain_text("silence counts as no", timeout=30_000)
    expect(case).to_contain_text("Covered: Omar takes it", timeout=30_000)
    expect(page.locator(".org-case")).to_have_count(4, timeout=60_000)  # the call-out, safety twice, the question
    expect(page.locator("#orgCases")).to_contain_text("Environmental Health and Safety")
    page.locator(".org-node[data-id='dining_gm']").click()
    expect(page.locator("#orgInbox")).to_contain_text("didn't answer in 30 minutes")
    assert page.errors == []


def test_judge_view_has_a_way_back_out(page, base_url):
    if "127.0.0.1" in base_url:
        pytest.skip("the /judge rewrite only exists on Vercel")
    page.goto(base_url + "/judge", wait_until="domcontentloaded")
    ready(page)
    page.get_by_role("link", name="Exit judge view").click()
    expect(page).to_have_url(re.compile(r"/$"))
    page.goto(base_url + "/judge", wait_until="domcontentloaded")
    ready(page)
    page.get_by_role("link", name="Org chart").click()
    expect(page.locator("#viewOrg")).to_be_visible()
    assert page.errors == []


def test_agent_graph_blocks_can_be_dragged(page, base_url):
    page.goto(base_url + "/#agents", wait_until="domcontentloaded")
    ready(page)
    broker = page.locator(".tof-node-broker")
    before = broker.bounding_box()
    page.mouse.move(before["x"] + 40, before["y"] + 20)
    page.mouse.down()
    page.mouse.move(before["x"] + 140, before["y"] + 90, steps=8)
    page.mouse.up()
    after = broker.bounding_box()
    assert after["x"] > before["x"] + 50 and after["y"] > before["y"] + 30
    page.get_by_role("button", name="Reset layout").click()
    assert abs(broker.bounding_box()["x"] - before["x"]) < 2
    assert page.errors == []


@pytest.mark.skipif(os.environ.get("TAGOUT_E2E_LIVE") != "1", reason="needs python -m scripts.run_all")
def test_live_system_runs_the_week(page):
    page.goto("http://127.0.0.1:8700/", wait_until="domcontentloaded")
    page.locator("#btnReset").click()
    page.wait_for_timeout(1500)
    page.locator("#btnSunday").click()
    page.wait_for_timeout(4000)
    page.locator("#btnRun").click()
    expect(page.locator("#kFixed")).to_contain_text("4", timeout=90_000)
    expect(page.locator("#kFixed")).to_contain_text("of 5")
    assert page.errors == []
