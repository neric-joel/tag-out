"""Download the curated Codex Pets into web/pets/ (git-ignored: the art is not redistributed in this repo).

    python -m scripts.fetch_pets            # all pets in seeds/pets.json
    python -m scripts.fetch_pets ana-only   # nothing special, kept simple

Also cuts PNG frames per mascot state for Telegram (Telegram photos don't animate a sprite sheet).
Sprite format: 8 columns, cells 192x208; rows: 0 idle, 3 waving, 4 jumping, 5 failed, 6 waiting, 8 review.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PETS = ROOT / "web" / "pets"
CELL_W, CELL_H = 192, 208
STATE_ROWS = {"idle": 0, "waving": 3, "jumping": 4, "failed": 5, "waiting": 6, "review": 8}


def fetch(pet: dict, client: httpx.Client) -> None:
    out = PETS / pet["id"]
    out.mkdir(parents=True, exist_ok=True)
    sheet_path = out / "spritesheet.webp"
    if not sheet_path.exists():
        sheet_path.write_bytes(client.get(pet["spritesheetUrl"]).raise_for_status().content)
    poster_path = out / "poster.webp"
    if not poster_path.exists():
        poster_path.write_bytes(client.get(pet["posterUrl"]).raise_for_status().content)
    Image.open(poster_path).convert("RGBA").save(out / "poster.png")
    sheet = Image.open(io.BytesIO(sheet_path.read_bytes())).convert("RGBA")
    for state, row in STATE_ROWS.items():
        frame = sheet.crop((0, row * CELL_H, CELL_W, (row + 1) * CELL_H))
        bg = Image.new("RGBA", (CELL_W + 64, CELL_H + 32), (246, 241, 232, 255))
        bg.alpha_composite(frame, (32, 16))
        bg.convert("RGB").save(out / f"{state}.png")


def main() -> None:
    pets = json.loads((ROOT / "seeds" / "pets.json").read_text(encoding="utf-8"))
    PETS.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "tag-out-hackathon/0.1"}) as c:
        for p in pets:
            try:
                fetch(p, c)
                print("ok  ", p["id"])
            except Exception as e:  # keep going; the UI falls back to the poster or a plain dot
                print("fail", p["id"], type(e).__name__, file=sys.stderr)


if __name__ == "__main__":
    main()
