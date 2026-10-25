"""Deterministic replay of the demo against a running system (start it with `python -m scripts.run_all`).

    python -m scripts.demo             # beat 2-4: Sunday check, rounds, ring + cover, commit
    python -m scripts.demo --callout   # after the week: Ben texts that he's sick, a same-day round covers Monday
    python -m scripts.demo --break-it  # beat 5: edit Dev's week before commit, abort, next proposal commits
    python -m scripts.demo --all       # week, call-out, then (after a reset) break it: for recording
"""

from __future__ import annotations

import argparse
import json
import time

import httpx

from core.net import registry

B = registry()["broker"]


def post(path: str, body: dict | None = None) -> dict:
    r = httpx.post(f"{B}{path}", json=body or {}, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def events() -> list[dict]:
    """Read the public event log the broker writes."""
    from core.net import RUNTIME

    path = RUNTIME / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wait_for(type_: str, after: int = 0, timeout: float = 120) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        for ev in events()[after:]:
            if ev["type"] == type_:
                return ev
        time.sleep(0.25)
    raise SystemExit(f"timed out waiting for {type_}")


def show(ev: dict) -> None:
    t = ev["type"]
    if t == "picks":
        picks = ", ".join(f"{a}->{s or 'pass'}" for a, s in ev["picks"].items())
        print(f"  [{ev['phase']} round {ev['iteration']}] {picks}")
    elif t in ("cycle", "chain", "prepare", "commit", "abort", "vote", "summary", "counter_window", "selected"):
        brief = {k: v for k, v in ev.items() if k not in ("n", "ts", "type", "moves")}
        print(f"  {t}: {brief}")


def beat_main(pause: float) -> dict:
    post("/admin/reset")
    time.sleep(pause)
    print("Sunday check")
    post("/demo/sunday")
    time.sleep(pause + 2.5)  # students tap "Find a trade"
    start = len(events())
    post("/demo/run")
    summary = wait_for("summary", start)
    for ev in events()[start:]:
        show(ev)
    return summary


def beat_callout(pause: float) -> dict:
    time.sleep(pause + 2)
    start = len(events())
    print("Ben texts his mascot: I woke up sick, can't make it Monday")
    httpx.post(f"{B}/phone/ben/text", json={"text": "I woke up sick, can't make it Monday"}, timeout=30)
    summary = wait_for("summary", start)
    for ev in events()[start:]:
        show(ev)
    return summary


def beat_break(pause: float) -> dict:
    post("/admin/reset")
    time.sleep(pause)
    post("/admin/auto", {"enabled": False, "agents": ["dev"], "delay": 1.5})
    post("/demo/sunday")
    time.sleep(pause + 2.5)
    httpx.post(f"{B}/phone/dev/tap", json={"data": "trade:yes:library-fri-1030-1000-d1"}, timeout=10)
    start = len(events())
    post("/demo/run")
    prep = wait_for("prepare", start)
    print(f"  ring {prep['proposal']} waiting for confirmations; Dev books physical therapy Thu 3pm")
    time.sleep(pause)
    post("/demo/break")
    wait_for("abort", start)
    post("/admin/auto", {"enabled": True, "agents": ["dev"], "delay": 1.5})
    summary = wait_for("summary", start, timeout=180)
    for ev in events()[start:]:
        show(ev)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--break-it", action="store_true")
    ap.add_argument("--callout", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pause", type=float, default=1.0)
    a = ap.parse_args()
    if a.all or not (a.break_it or a.callout):
        print("Beat 2-4:", beat_main(a.pause))
    if a.all or a.callout:
        print("Call-out:", beat_callout(a.pause))
    if a.all or a.break_it:
        print("Beat 5:", beat_break(a.pause))
    post("/admin/auto", {"enabled": True, "delay": 1.5})


if __name__ == "__main__":
    main()
