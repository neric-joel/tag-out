"""Record the demo video from the hosted replay (site/), with captions, title cards and background music.

    python -m scripts.record && python -m scripts.build_site     # the recording the page replays
    python -m scripts.video                                       # recordings/tagout_demo.mp4 (git-ignored)

Music: put a CC BY track at recordings/music/backed_vibes_clean.mp3 ("Backed Vibes Clean", Kevin MacLeod,
incompetech.com, CC BY 4.0) or pass --music. The credit is on the end card.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE, OUT = ROOT / "site", ROOT / "recordings"
W, H = 1440, 900

STYLE = """
#vcap { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 9999; max-width: 980px;
  background: #121212; color: #fff; font: 500 22px/30px "IBM Plex Sans", system-ui, sans-serif; padding: 14px 22px;
  border-radius: 14px; text-align: center; transition: opacity .35s; }
#vcap[data-off] { opacity: 0; }
#vcard { position: fixed; inset: 0; z-index: 10000; display: grid; place-items: center; background: #f6f1e7;
  font-family: "IBM Plex Sans", system-ui, sans-serif; color: #121212; transition: opacity .5s; }
#vcard[data-off] { opacity: 0; pointer-events: none; }
#vcard .sheet { width: 880px; border: 2px solid #121212; border-radius: 18px; padding: 44px 56px; background: #fffdf8;
  position: relative; }
#vcard .row { display: flex; justify-content: space-between; border-bottom: 1px dashed #9a958b; padding: 10px 0;
  font-size: 26px; }
#vcard h1 { font-size: 64px; margin: 0 0 8px; letter-spacing: -0.02em; }
#vcard p { font-size: 26px; line-height: 36px; margin: 10px 0; color: #3b3a37; }
#vcard .stamp { position: absolute; right: 40px; top: -22px; background: #fffdf8; transform: rotate(-9deg); border: 4px solid #c4242a;
  color: #c4242a; font: 700 30px/1 "IBM Plex Sans", sans-serif; padding: 8px 16px; border-radius: 10px; letter-spacing: .08em; }
#vcard .accent { color: #1d5fbf; }
#vcard small { display: block; margin-top: 22px; font-size: 16px; color: #6b6965; }
"""


def serve(directory: Path) -> tuple[str, http.server.ThreadingHTTPServer]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):  # the same rewrite as site/vercel.json
            return super().translate_path("/index.html" if path.split("?")[0] == "/judge" else path)

        def log_message(self, *a):
            pass

    handler = functools.partial(Handler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


class Tour:
    def __init__(self, page, base: str):
        self.page, self.base = page, base

    def prep(self) -> None:
        self.page.evaluate("""(css) => {
          if (document.getElementById('vstyle')) return;
          const s = document.createElement('style'); s.id = 'vstyle'; s.textContent = css; document.head.appendChild(s);
          const c = document.createElement('div'); c.id = 'vcap'; c.dataset.off = ''; document.body.appendChild(c);
          const k = document.createElement('div'); k.id = 'vcard'; k.dataset.off = ''; document.body.appendChild(k);
          document.querySelector('.static-banner')?.remove();
        }""", STYLE)

    def go(self, path: str, wait: float = 2.5) -> None:
        self.page.goto(self.base + path, wait_until="domcontentloaded")
        self.page.wait_for_timeout(int(wait * 1000))
        self.prep()

    def cap(self, text: str, hold: float) -> None:
        self.page.evaluate("(t) => { const c = document.getElementById('vcap'); c.textContent = t; delete c.dataset.off; }", text)
        self.page.wait_for_timeout(int(hold * 1000))

    def uncap(self) -> None:
        self.page.evaluate("() => { document.getElementById('vcap').dataset.off = ''; }")

    def card(self, html: str, hold: float) -> None:
        self.page.evaluate("(h) => { const k = document.getElementById('vcard'); k.innerHTML = h; delete k.dataset.off; }", html)
        self.page.wait_for_timeout(int(hold * 1000))
        self.page.evaluate("() => { document.getElementById('vcard').dataset.off = ''; }")
        self.page.wait_for_timeout(500)

    def click(self, selector: str) -> None:
        if not self.page.evaluate("(s) => { const e = document.querySelector(s); if (e) e.click(); return !!e; }", selector):
            raise RuntimeError(f"nothing to click: {selector} on {self.page.url}")

    def scroll(self, selector: str) -> None:
        self.page.evaluate("(s) => document.querySelector(s).scrollIntoView({behavior: 'smooth', block: 'start'})", selector)
        self.page.wait_for_timeout(900)


def run_tour(t: Tour) -> None:
    t.go("/#commons", 3)
    t.card("""<div class="sheet"><div class="stamp">OVER</div>
      <p>Ben is on an F-1 visa. He can work 20 hours a week across every campus job.</p>
      <div class="row"><span>Library shifts</span><b>8 h</b></div>
      <div class="row"><span>Aramark Dining (the Library can't see it)</span><b>9 h</b></div>
      <div class="row"><span>One cover a Library scheduler would hand him</span><b>+4 h</b></div>
      <div class="row"><span>Total</span><b style="color:#c4242a">21 of 20 h</b></div></div>""", 6.5)
    t.card("""<div class="sheet"><h1>Tag Out</h1>
      <p>Every ASU student worker gets a mascot agent. It holds their calendar, shifts and work-hour limits
      <span class="accent">privately</span>, and trades shifts with coworkers' mascots so nobody loses pay or breaks a
      limit their employer can't see.</p></div>""", 6)
    t.click("#btnSunday")
    t.page.wait_for_timeout(500)
    t.cap("Sunday 6 PM: each mascot checks next week against its own student's Canvas, calendar and texts.", 7)
    t.cap("Five find a collision and text their student. Only the shift id leaves a mascot, never the reason.", 7)
    t.cap("In each round a mascot answers the broker with one pick or a pass. A pass looks the same whatever the reason.", 8)
    t.cap("No ring yet: Ana's only option is her gym slot, so her mascot asks her instead of deciding.", 7)
    t.cap("She says yes. A three-way ring closes, and Ana, Dev and Ben all keep their hours and their pay.", 8)
    t.cap("Nothing moves until every student confirms and the manager approves. 4 of 5 fixed, $192 of pay kept.", 7)
    t.uncap()

    t.click("#whoPill")
    t.page.wait_for_timeout(1500)
    t.click("#people button[data-who='ben']")
    t.page.wait_for_timeout(1500)
    t.cap("Signed in as Ben: his week, his private chat with his mascot, and numbers only he sees.", 6)
    t.cap("17 of his 20 hours across all jobs, counting 9 at Aramark that the Library can't see.", 6)
    t.click("#meChips button")
    t.cap("Monday morning Ben wakes up sick. One text, and a cover round opens right away.", 7)
    t.cap("His manager hears at once, with no reason. Ben is told he's still on the schedule until a cover is approved.", 8)
    t.cap("Zoe takes the shift. The word “sick” never leaves Ben's mascot.", 6)
    t.uncap()

    t.go("/#manager", 2.5)
    t.cap("The manager's page: approvals, open shifts, reports. Never anyone's reasons, other jobs or visa status.", 7)
    t.click("#mgrExtra button[type=submit]")
    t.cap("The manager posts an extra shift. Every mascot is offered it and checks its own student's limits in private.", 8)
    t.cap("Ben and Dev pass without saying why. Zoe wants hours and fits, so she takes it.", 7)
    t.uncap()

    t.go("/#agents", 2.5)
    t.click("#agSunday")
    t.cap("How it works: every message between the agents, live. Six mascots, a broker and the Library's Steward.", 9)
    t.page.evaluate("() => document.querySelector('.tof-row')?.click()")
    t.cap("Click any message to read exactly what crossed. A pick is one shift id, or nothing.", 7)
    t.cap("Fields outside the closed schemas: 0. Private calendar labels in any message: 0.", 6)
    t.click("#agSnoop")
    t.page.wait_for_timeout(1200)
    t.scroll("#snoopNote")
    t.cap("A nosy broker asks every mascot why it passed. All six refuse, and none vouches for a shift it never picked.", 8)
    t.scroll("#claims")
    t.cap("Every number on the site traces to a rule quote, the simulator or a test.", 6)
    t.uncap()

    t.go("/judge", 4)
    t.scroll("#baseline")
    t.cap("The same week with a Library-only scheduler: Ben at 21 of 20 hours, Dev pushed over his 25-hour average.", 8)
    t.uncap()
    t.card("""<div class="sheet"><div class="stamp">TRADED</div><h1>Tag Out</h1>
      <p>Try it: <b class="accent">tag-out.vercel.app</b></p>
      <p>Code: github.com/neric-joel/tag-out</p>
      <small>Synthetic students and schedules. Not legal or immigration advice: your DSO and ASU Student Employment
      decide.<br>Music: "Backed Vibes Clean" by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0.</small></div>""", 7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", default=str(OUT / "music" / "backed_vibes_clean.mp3"))
    ap.add_argument("--url", help="record a deployed copy instead of serving site/ locally")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    base, httpd = (a.url.rstrip("/"), None) if a.url else serve(SITE)
    raw_dir = OUT / "raw_video"
    shutil.rmtree(raw_dir, ignore_errors=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(channel="msedge")
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(raw_dir),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        t0 = time.time()
        run_tour(Tour(page, base))
        path = page.video.path()
        ctx.close()
        browser.close()
    if httpd:
        httpd.shutdown()
    took = time.time() - t0
    out = OUT / "tagout_demo.mp4"
    music = Path(a.music)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(path)]
    if music.exists():
        fade = max(1.0, took - 4)
        cmd += ["-i", str(music), "-filter_complex",
                f"[1:a]volume=0.32,afade=t=in:d=1.5,afade=t=out:st={fade:.1f}:d=4[a]", "-map", "0:v", "-map", "[a]",
                "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", str(out)]
    subprocess.run(cmd, check=True)
    print(f"saved {out} ({took:.0f} s)")


if __name__ == "__main__":
    main()
