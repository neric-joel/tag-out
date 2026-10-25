"""A mascot's private reasoning. It sees its own student's whole life and answers peers with a pick or a pass.

Nothing in this module returns a reason to the network. Reasons go to the owner's diary and phone only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

from agents import explain
from agents.store import Store
from core.models import Collision, Shift
from core.timeutil import overlaps, week_start
from core.wire import (
    Decision,
    Eligibility,
    Move,
    Pick,
    PickRequest,
    Prepare,
    PublicFace,
    RingCheck,
    ShiftRef,
    TradeRequest,
    Vote,
)
from rulebook.rules import binding, check_change

Avail = Literal["yes", "unsure", "no"]
WAGE = 16.0


def to_shift(ref: ShiftRef) -> Shift:
    return Shift(id=ref.shift_id, employer=ref.employer, start=ref.start, end=ref.end, wage=WAGE)


class Brain:
    def __init__(
        self,
        store: Store,
        notify: Callable[[dict], Awaitable[None]],
        send_vote: Callable[[Vote], Awaitable[None]],
        send_trade: Callable[[TradeRequest], Awaitable[None]],
        names: Callable[[], dict[str, str]],
    ):
        self.store = store
        self._notify = notify
        self.send_vote = send_vote
        self.send_trade = send_trade
        self.names = names
        self.seen: dict[str, ShiftRef] = {}  # public roster facts about shifts offered in rounds
        self.auto_tasks: set[asyncio.Task] = set()

    @property
    def me(self) -> str:
        return self.store.student().id

    # ---------- messages to my own student ----------
    async def notify(self, text: str, buttons: list[tuple[str, str]] | None = None, kind: str = "info") -> None:
        msg = {"kind": kind, "text": text, "buttons": [{"label": a, "data": b} for a, b in (buttons or [])]}
        self.store.send(msg)
        await self._notify(msg)

    # ---------- weekly check ----------
    def collisions(self, monday: date) -> list[Collision]:
        out = []
        busy = self.store.busy()
        for s in self.store.shifts():
            if week_start(s.start.date()) != monday:
                continue
            for b in busy:
                if b.kind == "due" or not overlaps(s.start, s.end, b.start, b.end):
                    continue
                out.append(Collision(shift_id=s.id, shift_label=s.label, busy_id=b.id, busy_label=b.label,
                                     busy_kind=b.kind, source=b.source, week_of=monday))
                break
        return out

    async def sunday_check(self, monday: date) -> int:
        found = self.collisions(monday)
        st = self.store.student()
        self.store.put("collisions", [c.model_dump(mode="json") for c in found])
        if not found:
            self.store.note(f"Sunday check for the week of {monday:%b %d}: no collisions, stayed quiet.")
            return 0
        for c in found:
            self.store.note(f"Sunday check: {c.shift_label} hits {c.busy_label} ({c.source}).")
            await self.notify(explain.collision(st.name, c), [("Find a trade", f"trade:yes:{c.shift_id}"),
                                                             ("Not now", f"trade:no:{c.shift_id}")], kind="collision")
        return len(found)

    # ---------- availability (private) ----------
    def availability(self, ref: ShiftRef, giving: str | None = None) -> Avail:
        st = self.store.student()
        if ref.role not in st.job_profiles:
            return "no"  # Workday job profile: an instructional assistant can't cover a grader's shift
        if ref.start.weekday() in st.prefs.never_weekdays:
            return "no"
        if any(overlaps(ref.start, ref.end, b.start, b.end) for b in self.store.busy()):
            return "no"
        if any(s.id != giving and overlaps(ref.start, ref.end, s.start, s.end) for s in self.store.shifts()):
            return "no"
        for a in st.prefs.soft_avoid:
            if a.weekday == ref.start.weekday() and ref.start.hour < a.end_hour and a.start_hour < ref.end.hour:
                answer = self.store.get("answers", {}).get(ref.shift_id)
                return "yes" if answer == "yes" else "no" if answer == "no" else "unsure"
        return "yes"

    def rule_ok(self, add: list[Shift], drop: list[Shift]) -> bool:
        st = self.store.student()
        return check_change(st, self.store.shifts(), add=add, drop=drop, busy=self.store.busy()).ok

    # ---------- trade rounds ----------
    async def pick(self, req: PickRequest) -> Pick:
        for ref in req.items:
            self.seen[ref.shift_id] = ref
        st = self.store.student()
        give = self.store.shift(req.you_give) if req.you_give else None
        if req.phase == "cover" and not st.prefs.wants_more_hours:
            return Pick(round_id=req.round_id, iteration=req.iteration, agent_id=self.me, shift_id=None)
        drop = [give] if give else []
        if req.phase == "extend" and req.you_give and give is None:
            drop = [to_shift(self.seen[req.you_give])] if req.you_give in self.seen else []
        yes, unsure = [], []
        for ref in sorted(req.items, key=lambda r: r.start):
            if ref.owner == self.me:
                continue
            a = self.availability(ref, giving=req.you_give)
            if a == "no" or not self.rule_ok([to_shift(ref)], drop):
                continue
            (yes if a == "yes" else unsure).append(ref)
        if yes:
            choice = yes[0]
            self.store.note(f"Round {req.iteration} ({req.phase}): picked {to_shift(choice).label}.")
            return Pick(round_id=req.round_id, iteration=req.iteration, agent_id=self.me, shift_id=choice.shift_id)
        if unsure:
            await self.ask(unsure[0])
        else:
            self.store.note(f"Round {req.iteration} ({req.phase}): nothing fits, passed.")
        return Pick(round_id=req.round_id, iteration=req.iteration, agent_id=self.me, shift_id=None)

    async def ask(self, ref: ShiftRef) -> None:
        asked = self.store.get("asked", [])
        if ref.shift_id in asked:
            return
        self.store.put("asked", asked + [ref.shift_id])
        st = self.store.student()
        avoid = next(a for a in st.prefs.soft_avoid if a.weekday == ref.start.weekday())
        self.store.note(f"Passed for now: {to_shift(ref).label} is open but it's your {avoid.label} slot. Asked you.")
        await self.notify(explain.ask(to_shift(ref).label, avoid.label),
                          [("Take it", f"ask:yes:{ref.shift_id}"), ("Keep my slot", f"ask:no:{ref.shift_id}")],
                          kind="ask")

    # ---------- validation of the exact final ring ----------
    def my_moves(self, moves: list[Move]) -> tuple[list[Shift], list[Shift]]:
        adds = [to_shift(self.seen[m.shift_id]) for m in moves if m.to_agent == self.me and m.shift_id in self.seen]
        drops = [s for m in moves if m.from_agent == self.me and (s := self.store.shift(m.shift_id))]
        return adds, drops

    def ring_ok(self, moves: list[Move]) -> bool:
        adds, drops = self.my_moves(moves)
        wanted = [m for m in moves if m.to_agent == self.me]
        if len(adds) != len(wanted):
            return False
        giving = drops[0].id if drops else None
        if any(self.availability(self.seen[s.id], giving=giving) != "yes" for s in adds):
            return False
        return self.rule_ok(adds, drops)

    def check(self, rc: RingCheck) -> Eligibility:
        return Eligibility(ring_id=rc.ring_id, agent_id=self.me, ok=self.ring_ok(rc.moves))

    # ---------- two-phase commit ----------
    async def prepare(self, p: Prepare) -> Vote | None:
        if p.seen_version != self.store.version():
            return Vote(txn_id=p.txn_id, agent_id=self.me, vote="stale")
        if not self.ring_ok(p.moves):
            return Vote(txn_id=p.txn_id, agent_id=self.me, vote="no")
        self.store.put("hold", {"txn_id": p.txn_id, "ring_id": p.ring_id, "version": p.seen_version,
                                "moves": [m.model_dump() for m in p.moves]})
        adds, drops = self.my_moves(p.moves)
        st = self.store.student()
        text = explain.confirm(st, adds, drops, p.moves, self.names(), self.store.shifts(), self.store.busy())
        self.store.note(f"Holding {p.ring_id}: {text}")
        await self.notify(text, [("Confirm", f"confirm:{p.txn_id}"), ("Decline", f"decline:{p.txn_id}")],
                          kind="confirm")
        return None

    async def tap(self, data: str) -> str:
        parts = data.split(":")
        if parts[0] == "trade" and len(parts) == 3:
            if parts[1] == "yes":
                await self.send_trade(TradeRequest(agent_id=self.me, shift_id=parts[2]))
                self.store.note("You asked me to find a trade. Request sent: only the shift id left.")
                return "Looking for a trade. I'll text you when one works."
            return "OK, leaving it."
        if parts[0] == "ask" and len(parts) == 3:
            answers = self.store.get("answers", {})
            answers[parts[2]] = "yes" if parts[1] == "yes" else "no"
            self.store.put("answers", answers)
            self.store.note(f"You answered {answers[parts[2]]} about {parts[2]}.")
            return "Got it, I'll offer it in the next round." if parts[1] == "yes" else "OK, keeping your slot."
        if parts[0] in ("confirm", "decline") and len(parts) == 2:
            hold = self.store.get("hold")
            if not hold or hold["txn_id"] != parts[1]:
                return "That trade is no longer open."
            if parts[0] == "decline":
                await self.send_vote(Vote(txn_id=parts[1], agent_id=self.me, vote="no"))
                return "Declined. Nobody will be told why."
            vote = "yes" if hold["version"] == self.store.version() else "stale"
            await self.send_vote(Vote(txn_id=parts[1], agent_id=self.me, vote=vote))
            return "Confirmed. Waiting for the others." if vote == "yes" else "Your week changed, so I pulled out."
        return "?"

    async def decide(self, d: Decision) -> None:
        hold = self.store.get("hold")
        if not hold or hold["txn_id"] != d.txn_id:
            return
        moves = [Move(**m) for m in hold["moves"]]
        self.store.put("hold", None)
        if d.outcome == "abort":
            self.store.note(f"{hold['ring_id']} aborted. Shifts unchanged.")
            await self.notify(explain.aborted(), kind="abort")
            return
        adds, drops = self.my_moves(moves)
        self.store.set_shifts(adds, [s.id for s in drops])
        self.store.bump()
        made = int(self.store.get("trades_made", 0)) + 1
        self.store.put("trades_made", made)
        badges = set(self.store.get("badges", []))
        if len({m.to_agent for m in moves} | {m.from_agent for m in moves}) >= 3:
            badges.add("Chain Link")
        if made >= 3:
            badges.add("Streak")
        self.store.put("badges", sorted(badges))
        for s in drops:
            self.store.put("collisions", [c for c in self.store.get("collisions", []) if c["shift_id"] != s.id])
        self.store.note(f"{hold['ring_id']} committed.")
        await self.notify(explain.committed(adds, drops), kind="commit")

    async def schedule_changed(self) -> None:
        """Called after any edit to this student's week. A held trade with an old version must not commit."""
        self.store.bump()
        hold = self.store.get("hold")
        if hold and hold["version"] != self.store.version():
            await self.send_vote(Vote(txn_id=hold["txn_id"], agent_id=self.me, vote="stale"))
            self.store.note(f"Your week changed while {hold['ring_id']} was pending. Pulled out (stale).")

    # ---------- views ----------
    def public_face(self) -> PublicFace:
        st = self.store.student()
        return PublicFace(agent_id=st.id, name=st.name, pet_id=st.pet_id, state="idle",
                          trades_made=int(self.store.get("trades_made", 0)), badges=self.store.get("badges", []))

    def diary(self, monday: date) -> dict:
        """Owner-only. This is the only place the student's numbers are shown."""
        st = self.store.student()
        shifts = self.store.shifts()
        room = binding(st, shifts, monday)
        from rulebook.quotes import quote_for

        quote, url = quote_for(room.rule_id)
        return {
            "student": st.name, "pet_id": st.pet_id,
            "energy": {"rule_id": room.rule_id, "used": room.used, "cap": room.cap, "room": room.room,
                       "unit": room.unit, "quote": quote, "url": url},
            "shifts": [{"id": s.id, "label": s.label} for s in shifts if week_start(s.start.date()) == monday],
            "collisions": self.store.get("collisions", []),
            "diary": self.store.diary(),
            "version": self.store.version(),
        }
