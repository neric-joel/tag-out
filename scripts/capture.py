"""Headless captures of the running commons (real 60 fps animation, unlike a background browser tab).

    python -m scripts.capture frames            # 6 frames 1.5 s apart -> recordings/frames/
    python -m scripts.capture video --all       # record the demo (beats 2-5) -> recordings/demo.webm

Needs the system running (python -m scripts.run_all) and `pip install playwright`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "recordings"
URL = "http://127.0.0.1:8700/"


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(channel="chrome")  # fall back to the installed Chrome


def frames(n: int, gap: float, url: str, size: int | None) -> None:
    (OUT / "frames").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(url)
        if size:
            page.evaluate(f"localStorage.setItem('tagout.size', '{size}')")
            page.reload()
        page.wait_for_timeout(2500)
        for i in range(n):
            page.screenshot(path=str(OUT / "frames" / f"f{i:02d}.png"))
            gaps = page.evaluate("""() => { const ps = window.tagOutWorld.pets(), c = document.querySelector('#world');
              let m = 1e9; for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++)
              m = Math.min(m, Math.hypot((ps[i].x - ps[j].x) * c.clientWidth, (ps[i].y - ps[j].y) * 300));
              return { min: Math.round(m), states: ps.map(p => p.id + ':' + p.state).join(' ') }; }""")
            print(f"frame {i}: closest pair {gaps['min']} px | {gaps['states']}")
            page.wait_for_timeout(int(gap * 1000))
        b.close()


def video(url: str, demo_args: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(OUT / "raw"),
                            record_video_size={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(url)
        page.wait_for_timeout(3000)
        proc = subprocess.Popen([sys.executable, "-m", "scripts.demo", *demo_args], cwd=ROOT)
        while proc.poll() is None:
            page.wait_for_timeout(500)
        page.wait_for_timeout(4000)
        # a short tour: the roster after the trades, the simulation, then the judge view's comparison
        for sel, pause in ((".board", 4500), (".sim", 5000)):
            page.locator(sel).scroll_into_view_if_needed()
            page.wait_for_timeout(pause)
        page.goto(url.rstrip("/") + "/judge")
        page.wait_for_timeout(3000)
        page.locator("#baseline").scroll_into_view_if_needed()
        page.wait_for_timeout(6000)
        page.locator("#phonesRow").scroll_into_view_if_needed()
        page.wait_for_timeout(5000)
        path = page.video.path()
        ctx.close()
        b.close()
    final = OUT / "demo.webm"
    Path(path).replace(final)
    print("saved", final)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["frames", "video"])
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--gap", type=float, default=1.5)
    ap.add_argument("--size", type=int)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.mode == "frames":
        frames(a.n, a.gap, a.url, a.size)
    else:
        video(a.url, ["--all"] if a.all else [])
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
