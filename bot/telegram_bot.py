"""Telegram front door: each mascot's phone line. Run: python -m bot.telegram_bot

One bot, many students. A chat links itself to a mascot with /join <name>. Mascots and the Steward call POST /send
on this process; button taps go back to the owning mascot. Messages only ever go to chats that pressed /start.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.net import RUNTIME, Net, registry
from ingest.llm import secret
from seeds.scenario import STUDENTS

ROOT = Path(__file__).resolve().parent.parent
PETS_DIR = ROOT / "web" / "pets"
LINKS = RUNTIME / "bot_links.json"
FOOTER = "Not legal or immigration advice. Your DSO and ASU Student Employment decide."
log = logging.getLogger("tagout.bot")


class Links:
    """chat id <-> mascot id, persisted so a restart keeps everyone linked."""

    def __init__(self, path: Path = LINKS):
        self.path = path
        self.data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))

    def link(self, chat_id: int, who: str) -> None:
        self.data = {c: w for c, w in self.data.items() if w != who}  # one phone per mascot
        self.data[str(chat_id)] = who
        self.save()

    def who(self, chat_id: int) -> str | None:
        return self.data.get(str(chat_id))

    def chat(self, who: str) -> int | None:
        return next((int(c) for c, w in self.data.items() if w == who), None)


class TagOutBot:
    def __init__(self, token: str, reg: dict | None = None, net: Net | None = None, links: Links | None = None):
        self.reg = reg or registry()
        self.net = net or Net()
        self.links = links or Links()
        self.names = {s["id"]: s["name"] for s in STUDENTS} | {"manager": "Library manager"}
        self.app = Application.builder().token(token).build()
        for cmd, fn in [("start", self.start), ("join", self.join), ("pet", self.pet), ("week", self.week),
                        ("diary", self.diary), ("sunday", self.sunday), ("trade", self.trade),
                        ("help", self.start)]:
            self.app.add_handler(CommandHandler(cmd, fn))
        self.app.add_handler(CallbackQueryHandler(self.on_tap))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))

    def url(self, who: str) -> str:
        return self.reg["steward"] if who == "manager" else self.reg["agents"][who]

    # ----- commands -----
    async def start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        who = self.links.who(update.effective_chat.id)
        hello = (f"You're linked to {self.names[who]}'s mascot." if who else
                 "Hi, I'm Tag Out. I read your calendar and your shifts, warn you on Sundays when they collide, "
                 "and trade shifts with your coworkers' mascots so nobody loses pay. I never tell anyone why "
                 "you said no.\n\nDemo: link this chat with /join ana (or ben, dev, priya, zoe, marco, manager).")
        await update.message.reply_text(hello + "\n\n" + FOOTER)

    async def join(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        who = (ctx.args[0].lower() if ctx.args else "")
        if who not in self.names:
            await update.message.reply_text("Usage: /join ana | ben | dev | priya | zoe | marco | manager")
            return
        self.links.link(update.effective_chat.id, who)
        msg = f"This chat is now {self.names[who]}'s phone."
        if who != "manager":
            msg += " Text me things like \"dentist Thu 3pm\". /pet picks your mascot, /week shows your shifts."
        await update.message.reply_text(msg)

    async def pet(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Mascots live on the Tag Out website: open it, click \"Pets\" and pick "
                                        "yours. No two people on a roster share one.")

    async def week(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        who = self.links.who(update.effective_chat.id)
        if not who or who == "manager":
            await update.message.reply_text("Link a student first: /join ana")
            return
        d = await self.owner_get(who, "/diary")
        lines = [f"- {s['label']}" for s in d["shifts"]] or ["no shifts"]
        await update.message.reply_text("Your Library shifts this week:\n" + "\n".join(lines))

    async def diary(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        who = self.links.who(update.effective_chat.id)
        if not who or who == "manager":
            return
        d = await self.owner_get(who, "/diary")
        e = d["energy"]
        unit = "$" if e["unit"] == "$" else "h"
        room = f"${e['room']:.0f}" if unit == "$" else f"{e['room']:g} h"
        text = (f"Private, only you see this.\nRoom before your tightest limit: {room} ({e['rule_id']}).\n"
                f"\"{e['quote']}\"\n{e['url']}")
        await update.message.reply_text(text, disable_web_page_preview=True)

    async def sunday(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self.net.post(f"{self.reg['broker']}/demo/sunday")
        await update.message.reply_text("Sunday check sent to every mascot.")

    async def trade(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self.net.post(f"{self.reg['broker']}/demo/run")
        await update.message.reply_text("Trade rounds started. Watch the arena.")

    # ----- student texts and taps -----
    async def on_text(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        who = self.links.who(update.effective_chat.id)
        if not who or who == "manager":
            await update.message.reply_text("Link this chat first: /join ana")
            return
        r = await self.owner_post(who, "/intake", {"text": update.message.text})
        await update.message.reply_text(r.get("reply", "Noted."))

    async def on_tap(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        who = self.links.who(q.message.chat.id)
        if not who:
            return
        if q.data.startswith("pet:"):
            r = await self.owner_post(who, "/pet", {"pet_id": q.data[4:]})
            await q.edit_message_text(r.get("reply", "Saved."))
            return
        r = await self.owner_post(who, "/tap", {"data": q.data})
        label = next((b.text for row in q.message.reply_markup.inline_keyboard for b in row
                      if b.callback_data == q.data), "")
        body = q.message.text or q.message.caption or ""
        new = f"{body}\n\n> {label}. {r.get('reply', '')}"
        if q.message.text:
            await q.edit_message_text(new)
        else:
            await q.edit_message_caption(new)

    # ----- owner channel calls (token from the mascot's own runtime file) -----
    def token(self, who: str) -> dict:
        p = RUNTIME / "tokens" / f"{who}.txt"
        return {"X-Owner-Token": p.read_text().strip()} if p.exists() else {}

    async def owner_get(self, who: str, path: str) -> dict:
        r = await self.net.client.get(f"{self.url(who)}{path}", headers=self.token(who))
        r.raise_for_status()
        return r.json()

    async def owner_post(self, who: str, path: str, body: dict) -> dict:
        r = await self.net.client.post(f"{self.url(who)}{path}", json=body, headers=self.token(who))
        r.raise_for_status()
        return r.json()

    # ----- outbound from mascots -----
    async def send(self, who: str, kind: str, text: str, buttons: list[dict]) -> bool:
        chat = self.links.chat(who)
        if chat is None:
            return False
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(b["label"], callback_data=b["data"])
                                        for b in buttons]]) if buttons else None
        # Plain text only: the mascots live on the website, the phone just carries the message.
        await self.app.bot.send_message(chat, text, reply_markup=markup)
        return True


def internal_api(bot: TagOutBot) -> FastAPI:
    api = FastAPI(title="Tag Out bot relay")

    @api.post("/send")
    async def send(body: dict) -> dict:
        try:
            ok = await bot.send(body["student_id"], body.get("kind", "info"), body["text"], body.get("buttons", []))
        except Exception as e:
            log.warning("send failed: %s", type(e).__name__)
            ok = False
        return {"delivered": ok}

    @api.get("/links")
    async def links() -> dict:
        return {"linked": sorted(set(bot.links.data.values()))}

    return api


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # never log request URLs (they hold the token)
    token = secret("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing in api.env; the demo still runs with on-screen phones.")
    bot = TagOutBot(token)
    port = int(registry()["bot"].rsplit(":", 1)[1])
    server = uvicorn.Server(uvicorn.Config(internal_api(bot), host="127.0.0.1", port=port, log_level="warning"))
    async with bot.app:
        await bot.app.start()
        await bot.app.updater.start_polling(drop_pending_updates=True)
        me = await bot.app.bot.get_me()
        log.info("polling as @%s; relay on :%d", me.username, port)
        try:
            await server.serve()
        finally:
            await bot.app.updater.stop()
            await bot.app.stop()


if __name__ == "__main__":
    os.environ.setdefault("TAGOUT_MODE", "live")
    asyncio.run(main())
