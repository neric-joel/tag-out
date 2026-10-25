"""Cubbie Skill client for a student's Tag Out mascot. Standard library only (Cubbie's sandbox).

    python tagout.py setup --mascot-url https://... (token from TAGOUT_OWNER_TOKEN)
    python tagout.py sync --source canvas --events canvas.json
    python tagout.py inbox
    python tagout.py answer <choice code>
    python tagout.py tell "dentist Thu 3pm"
    add --sample to any command to run offline on assets/

Everything here talks only to the student's own mascot, through its owner channel.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "tag-out"
CONFIG = CONFIG_DIR / "config.json"
STATE = CONFIG_DIR / "state.json"
MAX_OUT = 7500  # Cubbie reads up to 8,000 characters of output


def fail(msg: str) -> None:
    print(f"error: {msg}")
    sys.exit(1)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def call(method: str, path: str, body: dict | None = None) -> dict:
    cfg = load(CONFIG, None)
    if not cfg:
        fail("not set up (run setup first)")
    req = urllib.request.Request(cfg["mascot_url"].rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Owner-Token": cfg["token"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        fail("the mascot refused the token" if e.code == 403 else f"the mascot answered {e.code}")
    except (urllib.error.URLError, TimeoutError):
        fail("the mascot was unreachable")
    return {}


def show(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        if m.get("kind") in ("student", "reply"):
            continue
        lines.append(m["text"])
        for i, b in enumerate(m.get("buttons") or [], 1):
            lines.append(f"  {i}. {b['label']}  (code: {b['data']})")
    return "\n".join(lines)[:MAX_OUT] or "nothing new"


def sample(cmd: str, args) -> None:
    """Offline walk-through on the bundled sample week."""
    msgs = load(HERE / "assets" / "sample_inbox.json", [])
    if cmd == "sync":
        events = load(Path(args.events) if args.events else HERE / "assets" / f"sample_{args.source}.json", [])
        print(f"sample: would send {len(events)} {args.source} items to your mascot as private busy blocks")
    elif cmd == "inbox":
        print(show(msgs))
    elif cmd == "answer":
        print({"trade": "Looking for a trade. I'll text you when one works.",
               "ask": "Got it, I'll offer it in the next round.",
               "confirm": "Confirmed. Waiting for the others."}.get(args.code.split(":")[0], "OK."))
    elif cmd == "tell":
        print(f"sample: your mascot would note \"{args.text}\" as busy time; only 'busy' ever leaves it")
    elif cmd == "setup":
        print("sample: setup skipped")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tag Out mascot client for Cubbie")
    ap.add_argument("--sample", action="store_true", help="offline, uses assets/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--mascot-url", required=False)
    s = sub.add_parser("sync")
    s.add_argument("--source", choices=["canvas", "calendar", "gmail"], required=True)
    s.add_argument("--events")
    sub.add_parser("inbox")
    s = sub.add_parser("answer")
    s.add_argument("code")
    s = sub.add_parser("tell")
    s.add_argument("text")
    args = ap.parse_args()

    if args.sample:
        sample(args.cmd, args)
        return
    if args.cmd == "setup":
        token = os.environ.get("TAGOUT_OWNER_TOKEN", "").strip()
        if not args.mascot_url or not token:
            fail("need --mascot-url and the TAGOUT_OWNER_TOKEN secret")
        save(CONFIG, {"mascot_url": args.mascot_url, "token": token})
        save(STATE, {"seen": 0})
        print("set up: your Cubbie can now reach your Tag Out mascot")
    elif args.cmd == "sync":
        if not args.events:
            fail("need --events <file.json>")
        events = load(Path(args.events), None)
        if not isinstance(events, list):
            fail("events file must be a JSON list")
        r = call("POST", "/import", {"source": args.source, "events": events})
        print(f"sent {r.get('imported', 0)} {args.source} items to your mascot (kept private)")
    elif args.cmd == "inbox":
        st = load(STATE, {"seen": 0})
        r = call("GET", f"/phone?since={int(st.get('seen', 0))}")
        msgs = r.get("messages", [])
        if msgs:
            st["seen"] = max(m["n"] for m in msgs)
            save(STATE, st)
        print(show(msgs))
    elif args.cmd == "answer":
        print(call("POST", "/tap", {"data": args.code}).get("reply", "OK."))
    elif args.cmd == "tell":
        print(call("POST", "/intake", {"text": args.text}).get("reply", "Noted."))


if __name__ == "__main__":
    main()
