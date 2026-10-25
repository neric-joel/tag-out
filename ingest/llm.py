"""Thin Claude wrapper: cache every response, track spend, never log secrets.

Lookup order: seeds/llm_cache (committed, synthetic demo texts only) then cache/llm (git-ignored, real texts).
TAGOUT_OFFLINE=1 or a missing key means cache-only; callers fall back to deterministic code on a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_CACHE = ROOT / "seeds" / "llm_cache"
RUN_CACHE = ROOT / "cache" / "llm"
SPEND = Path(os.environ.get("TAGOUT_SPEND_FILE", ROOT / "cache" / "spend.json"))
ENV_FILE = Path(os.environ.get("TAGOUT_ENV_FILE", ROOT.parent.parent / "api.env"))
# Hard stop: no call is made once this much has been spent (TAGOUT_SPEND_CAP overrides). The key has about $99:
# up to $35 for building and test runs, $15 for recording the demo, and at least $45 kept for judges.
BUDGET_USD = float(os.environ.get("TAGOUT_SPEND_CAP", "15"))
PARSE_MODEL = "claude-haiku-5-5"
EXPLAIN_MODEL = "claude-sonnet-5-5"
# rough $ per million tokens (input, output); used only to stop well before the budget
PRICES = {PARSE_MODEL: (1.0, 5.0), EXPLAIN_MODEL: (3.0, 15.0)}


def load_env() -> dict[str, str]:
    """KEY=VALUE lines from api.env; a lone line with no '=' is the Anthropic key."""
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    lines = [ln.strip() for ln in ENV_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) == 1 and "=" not in lines[0]:
        return {"ANTHROPIC_API_KEY": lines[0]}
    for ln in lines:
        if "=" in ln:
            k, v = (p.strip() for p in ln.split("=", 1))
            out[k] = v
    return out


def secret(name: str) -> str | None:
    return os.environ.get(name) or load_env().get(name)


def offline() -> bool:
    return os.environ.get("TAGOUT_OFFLINE") == "1" or not secret("ANTHROPIC_API_KEY")


def cache_key(model: str, payload: dict[str, Any]) -> str:
    blob = json.dumps({"model": model, **payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def cache_get(key: str) -> dict | None:
    for d in (SEED_CACHE, RUN_CACHE):
        p = d / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def cache_put(key: str, value: dict, seed: bool = False) -> None:
    d = SEED_CACHE if seed else RUN_CACHE
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(value, indent=1, sort_keys=True), encoding="utf-8")


def spent() -> float:
    return json.loads(SPEND.read_text())["usd"] if SPEND.exists() else 0.0


def _record(model: str, usage) -> None:
    pin, pout = PRICES.get(model, (3.0, 15.0))
    usd = spent() + (usage.input_tokens * pin + usage.output_tokens * pout) / 1e6
    SPEND.parent.mkdir(parents=True, exist_ok=True)
    SPEND.write_text(json.dumps({"usd": round(usd, 5)}))


def call_tool(model: str, system: str, user: str, tool: dict, seed: bool = False,
              max_tokens: int = 800) -> dict | None:
    """Force one tool call and return its input dict. Cached; None when offline and not cached."""
    key = cache_key(model, {"system": system, "user": user, "tool": tool})
    hit = cache_get(key)
    if hit is not None:
        return hit
    if offline() or spent() >= BUDGET_USD:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"))
    try:
        msg = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
        )
    except anthropic.APIError as e:
        print(f"[llm] {model} call failed: {type(e).__name__}")
        return None
    _record(model, msg.usage)
    block = next((b for b in msg.content if b.type == "tool_use"), None)
    if block is None:
        return None
    cache_put(key, block.input, seed=seed)
    return block.input


def call_text(model: str, system: str, user: str, seed: bool = False, max_tokens: int = 300) -> str | None:
    key = cache_key(model, {"system": system, "user": user, "kind": "text"})
    hit = cache_get(key)
    if hit is not None:
        return hit["text"]
    if offline() or spent() >= BUDGET_USD:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"))
    try:
        msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": user}])
    except anthropic.APIError as e:
        print(f"[llm] {model} call failed: {type(e).__name__}")
        return None
    _record(model, msg.usage)
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    cache_put(key, {"text": text}, seed=seed)
    return text
