"""Build the hosted replay into site/ (Vercel serves it as static files).

    python -m scripts.record       # site/data/*.json, recorded from the real system
    python -m scripts.build_site   # site/index.html, site/web/, site/vercel.json

The pet art is not copied: the page loads each sprite sheet from codex-pets.net, where its creators published it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB, SITE = ROOT / "web", ROOT / "site"


def main() -> None:
    if not (SITE / "data" / "tour.json").exists():
        raise SystemExit("run python -m scripts.record first")
    shutil.rmtree(SITE / "web", ignore_errors=True)
    shutil.copytree(WEB, SITE / "web", ignore=shutil.ignore_patterns("pets", "*.html"))
    sheets = {p["id"]: p["spritesheetUrl"] for p in json.loads((ROOT / "seeds" / "pets.json").read_text(encoding="utf-8"))}
    boot = ("<script>window.TAGOUT_STATIC = true; const TAGOUT_SHEETS = " + json.dumps(sheets)
            + "; window.TAGOUT_PET_URL = (id) => TAGOUT_SHEETS[id] || '';</script>\n")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('<script src="/web/js/world.js', boot + '<script src="/web/js/world.js', 1)
    (SITE / "index.html").write_text(html, encoding="utf-8")
    # the code behind /api/try (site/api/try.py), without OR-Tools: broker/cpsat.py falls back to an exact search
    app = SITE / "app"
    shutil.rmtree(app, ignore_errors=True)
    skip = shutil.ignore_patterns("__pycache__", "*.db", "pets")
    for pkg in ("agents", "broker", "core", "ingest", "org", "rulebook", "seeds", "steward", "config"):
        shutil.copytree(ROOT / pkg, app / pkg, ignore=skip)
    (app / "scripts").mkdir(parents=True)
    for f in ("__init__.py", "inproc.py", "record.py"):
        shutil.copy2(ROOT / "scripts" / f, app / "scripts" / f)
    (app / "docs").mkdir()
    for f in ("rule_quotes.json", "simulation.json", "RULES.md"):
        shutil.copy2(ROOT / "docs" / f, app / "docs" / f)
    reqs = ["fastapi>=0.115", "httpx>=0.27", "pydantic>=2.8", "icalendar>=6", "recurring-ical-events>=3", "pyyaml>=6",
            "sse-starlette>=2", "tzdata"]
    (SITE / "requirements.txt").write_text("\n".join(reqs) + "\n", encoding="utf-8")
    (SITE / "vercel.json").write_text(json.dumps({
        "functions": {"api/try.py": {"maxDuration": 60}},
        "rewrites": [{"source": "/judge", "destination": "/index.html"}],
        "headers": [{"source": "/data/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=300"}]}],
    }, indent=1), encoding="utf-8")
    files = sorted(str(f.relative_to(SITE)).replace("\\", "/") for f in SITE.rglob("*") if f.is_file())
    print(f"site/: {len(files)} files")


if __name__ == "__main__":
    main()
