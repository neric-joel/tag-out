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
    (SITE / "vercel.json").write_text(json.dumps({
        "rewrites": [{"source": "/judge", "destination": "/index.html"}],
        "headers": [{"source": "/data/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=300"}]}],
    }, indent=1), encoding="utf-8")
    files = sorted(str(f.relative_to(SITE)).replace("\\", "/") for f in SITE.rglob("*") if f.is_file())
    print(f"site/: {len(files)} files")


if __name__ == "__main__":
    main()
