"""Start the whole system as separate processes: 6 Library mascots, the Steward, the Broker (+ arena), the campus
hierarchy (10 more mascots and the role agents above them, scripts/run_org.py) and the Telegram bot.

    python -m scripts.run_all                # auto mode: synthetic students tap their own buttons
    python -m scripts.run_all --mode live    # wait for real taps (Telegram or the on-screen phones)
    python -m scripts.run_all --no-bot       # without Telegram

Open http://127.0.0.1:8700 for the arena. Ctrl+C stops everything.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

from core.net import RUNTIME
from ingest.llm import secret
from seeds.org import ROLES
from seeds.scenario import STUDENTS

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def write_registry() -> dict:
    from scripts.run_org import ports

    org = {who: f"http://127.0.0.1:{p}" for who, p in ports().items()} | {"steward": "http://127.0.0.1:8701"}
    reg = {"agents": {s["id"]: f"http://127.0.0.1:{s['port']}" for s in STUDENTS},
           "broker": "http://127.0.0.1:8700", "steward": "http://127.0.0.1:8701", "bot": "http://127.0.0.1:8702",
           "org": org, "coordinators": {f"org-{r}-": org[r] for r in ROLES if r != "steward"},
           "org_key": secrets.token_hex(16)}  # signs the hierarchy's own messages (escalations, case updates)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "registry.json").write_text(json.dumps(reg, indent=1))
    return reg


def join_codes() -> dict[str, str]:
    """One code per student and the manager, so a Telegram chat can't join as someone else by typing a name.
    Kept across restarts so phones stay linked; delete runtime/join_codes.json to issue new ones."""
    path = RUNTIME / "join_codes.json"
    if path.exists():
        return json.loads(path.read_text())
    codes = {who: secrets.token_hex(3).upper() for who in [s["id"] for s in STUDENTS] + ["manager"]}
    path.write_text(json.dumps(codes, indent=1))
    return codes


def uvicorn(module: str, port: int, env: dict, log: Path) -> subprocess.Popen:
    return subprocess.Popen([PY, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env, stdout=log.open("w"),
                            stderr=subprocess.STDOUT)


def wait_up(urls: list[str], timeout: float = 40) -> None:
    end = time.time() + timeout
    pending = set(urls)
    while pending and time.time() < end:
        for u in list(pending):
            try:
                httpx.get(u, timeout=1)
                pending.discard(u)
            except httpx.HTTPError:
                pass
        time.sleep(0.3)
    if pending:
        raise SystemExit(f"not up: {sorted(pending)} (see runtime/logs)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auto", "live"], default="auto")
    ap.add_argument("--no-bot", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="delete mascot databases first")
    ap.add_argument("--delay", type=float, default=2.0, help="auto-tap delay in seconds")
    args = ap.parse_args()

    reg = write_registry()
    join_codes()  # before the bot starts, so /join always needs a code
    logs = RUNTIME / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        for f in RUNTIME.glob("mascot_*.db"):
            f.unlink()
    (RUNTIME / "events.jsonl").unlink(missing_ok=True)
    base = os.environ | {"TAGOUT_DEBUG": "1", "TAGOUT_MODE": args.mode, "TAGOUT_AUTO_DELAY": str(args.delay),
                         "PYTHONPATH": str(ROOT)}
    procs: list[subprocess.Popen] = []
    for s in STUDENTS:
        procs.append(uvicorn("agents.mascot:app", s["port"], base | {"TAGOUT_STUDENT": s["id"]},
                             logs / f"mascot_{s['id']}.log"))
    procs.append(uvicorn("steward.app:app", 8701, base | {"TAGOUT_ROLE": "steward"}, logs / "steward.log"))
    procs.append(uvicorn("broker.app:app", 8700, base | {"TAGOUT_ROLE": "broker"}, logs / "broker.log"))
    procs.append(subprocess.Popen([PY, "-m", "scripts.run_org"], cwd=ROOT, env=base,
                                  stdout=(logs / "org.log").open("w"), stderr=subprocess.STDOUT))
    wait_up([f"{u}/public" for u in reg["agents"].values()] + [f"{reg['steward']}/roster", f"{reg['broker']}/agents"]
            + [f"{u}/phone" for r, u in reg["org"].items() if r != "steward"])
    bot_on = False
    if not args.no_bot and secret("TELEGRAM_BOT_TOKEN"):
        procs.append(subprocess.Popen([PY, "-m", "bot.telegram_bot"], cwd=ROOT, env=base,
                                      stdout=(logs / "bot.log").open("w"), stderr=subprocess.STDOUT))
        try:
            wait_up([f"{reg['bot']}/links"], timeout=30)
            bot_on = True
        except SystemExit:
            print("Telegram bot did not start (see runtime/logs/bot.log); continuing with on-screen phones.")
    print(f"Tag Out is up ({args.mode} mode). 6 Library mascots on :8711-8716, steward :8701, broker :8700, "
          "campus hierarchy :8721-8740"
          + (", Telegram bot on" if bot_on else ", no Telegram bot"))
    print("Commons: http://127.0.0.1:8700        Judge view: http://127.0.0.1:8700/judge")
    if bot_on:
        codes = join_codes()
        print("Telegram join codes (send /join <name> <code> to the bot): "
              + ", ".join(f"{who} {code}" for who, code in codes.items()))
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        dead = [p.args for p in procs if p.poll() is not None]
        print("a process exited:", dead, "- see runtime/logs")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
