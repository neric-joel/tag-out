"""Quote checker: a rule may only cite text that appears verbatim in docs/RULES.md."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_MD = ROOT / "docs" / "RULES.md"
QUOTES_JSON = ROOT / "docs" / "rule_quotes.json"


@lru_cache(maxsize=1)
def rules_text() -> str:
    return RULES_MD.read_text(encoding="utf-8") if RULES_MD.exists() else ""


@lru_cache(maxsize=1)
def quotes() -> dict[str, dict[str, str]]:
    if not QUOTES_JSON.exists():
        return {}
    return json.loads(QUOTES_JSON.read_text(encoding="utf-8"))


def quote_for(rule_id: str) -> tuple[str | None, str | None]:
    """Return (quote, url) only if the quote really exists in RULES.md; otherwise (None, url)."""
    entry = quotes().get(rule_id) or {}
    quote, url = entry.get("quote"), entry.get("url")
    if quote and quote in rules_text():
        return quote, url
    return None, url


def unverified_quotes() -> list[str]:
    """Rule ids whose quote is missing from RULES.md. The test suite requires this to be empty."""
    text = rules_text()
    return [rid for rid, e in quotes().items() if not e.get("quote") or e["quote"] not in text]
