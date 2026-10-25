"""A mascot's private reasoning. It sees its own student's whole life and answers peers with a pick or a pass.

Nothing in this module returns a reason to the network. Reasons go to the owner's diary and phone only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Literal

from agents import explain
from agents.store import Store
from core.models import BusyBlock, Collision, Shift
from core.timeutil import at, fmt_span, overlaps, week_start
from core.wire import (
    Decision,
    Eligibility,
    IssueReport,
    MeetingBook,
    MeetingInvite,
    MeetingOptions,
    MeetingRequest,
    Move,
    Pick,
    PickRequest,
    Prepare,
    PublicFace,
    RingCheck,
    Rsvp,
    ShiftRef,
    TradeRequest,
    Vote,
)
from rulebook.rules import (
    binding,
    check_change,
    f1_cap_for,
    fws_runway,
    near_f1_limit,
    next_break,
    rooms,
    week_hours,
)

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
        to_steward: Callable[[str, object], Awaitable[dict]] | None = None,
    ):
        self.store = store
        self._notify = notify
        self.send_vote = send_vote
        self.send_trade = send_trade
        self.names = names
        self.to_steward = to_steward
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
        runway = fws_runway(st, self.store.shifts(), monday)
        if runway and self.store.get("fws_warned") != str(next_break(monday)):
            self.store.put("fws_warned", str(next_break(monday)))  # once before each break, not every Sunday
            self.store.note(f"Work-Study award lasts about {runway[0]:.1f} weeks at this week's pay. Told you.")
            await self.notify(explain.fws_runway(*runway, st.limits.fws_award_remaining or 0), kind="info")
        if not found:
            self.store.note(f"Sunday check for the week of {monday:%b %d}: no collisions, stayed quiet.")
            return 0
        for c in found:
            self.store.note(f"Sunday check: {c.shift_label} hits {c.busy_label} ({c.source}).")
            await self.notify(explain.collision(st.name, c), [("Find a trade", f"trade:yes:{c.shift_id}"),
                                                             ("Not now", f"trade:no:{c.shift_id}")], kind="collision")
        return len(found)

    # ---------- same-day call-out ----------
    async def call_out(self, want: dict, monday: date) -> str:
        """'I'm sick, tag me out of Thursday': find that shift and ask the broker for a round now.

        `want` is ingest.text.callout()'s weekday and hour. The reason stays here; the broker gets a shift id."""
        done = set(self.store.get("called_out", []))
        mine = sorted((s for s in self.store.shifts() if week_start(s.start.date()) == monday and s.id not in done),
                      key=lambda s: s.start)
        if want.get("weekday") is not None:
            mine = [s for s in mine if s.start.weekday() == want["weekday"]]
        if want.get("hour") is not None and len(mine) > 1:
            mine = [s for s in mine if s.start.hour <= want["hour"] < s.end.hour] or mine
        if len(mine) == 1:
            return await self.tag_out(mine[0].id)
        if not mine:
            return "I couldn't find a shift of yours then. Which day is it?"
        await self.notify("Which shift should I tag you out of?", [(s.label, f"out:{s.id}") for s in mine[:4]],
                          kind="ask")
        return "Which shift? Tap one."

    async def tag_out(self, shift_id: str) -> str:
        s = next((x for x in self.store.shifts() if x.id == shift_id), None)
        if s is None:
            return "That shift isn't yours any more."
        self.store.put("called_out", [*self.store.get("called_out", []), shift_id])
        self.remember("requested", shift_id)
        self.store.add_busy([BusyBlock(id=f"out-{shift_id}", start=s.start, end=s.end, kind="other",
                                       label="Called out", source="text")])
        await self.schedule_changed()
        await self.send_trade(TradeRequest(agent_id=self.me, shift_id=shift_id, urgent=True))
        self.store.note(f"You called out of {s.label}. Asked for a round now; only the shift id left, no reason.")
        return (f"Asking your coworkers to cover your {s.label} now. You're still on the schedule until someone "
                "confirms and your manager approves, so also follow your department's call-out rule (usually: tell "
                "your supervisor directly). Your reason stays with me; your manager only hears it's a same-day "
                "request.")

    # ---------- work life beyond trades: issues, meetings, extra hours ----------
    async def draft_issue(self, text: str, category: str) -> str:
        issues = self.store.get("issues", {})
        iid = f"issue-{self.me}-{len(issues) + 1}"
        issues[iid] = {"text": text, "category": category, "status": "draft"}
        self.store.put("issues", issues)
        await self.notify(explain.issue_draft(text, category),
                          [("Send with my name", f"issue:named:{iid}"), ("Send anonymously", f"issue:anon:{iid}"),
                           ("Don't send", f"issue:no:{iid}")], kind="ask")
        return "I wrote it up. Check it and choose how to send it."

    async def send_issue(self, mode: str, iid: str) -> str:
        issues = self.store.get("issues", {})
        it = issues.get(iid)
        if not it or it["status"] != "draft":
            return "That report is already handled."
        if mode == "no":
            it["status"] = "dropped"
            self.store.put("issues", issues)
            return "OK, not sent."
        named = mode == "named"
        await self.to_steward("/issue", IssueReport(issue_id=iid, category=it["category"], text=it["text"],
                                                    agent_id=self.me if named else None))
        it["status"] = "sent"
        self.store.put("issues", issues)
        self.store.note(f"Sent your {it['category']} report to your manager" + ("." if named else ", anonymously."))
        return ("Sent to your manager with your name. I'll tell you when they've seen it." if named
                else "Sent anonymously. Your manager can't see who sent it, so they can't reply to you.")

    async def issue_acked(self, iid: str) -> None:
        it = self.store.get("issues", {}).get(iid)
        if it:
            await self.notify(f"Your manager saw your report: \"{it['text']}\"", kind="info")

    def free_slots(self, monday: date, minutes: int) -> list[tuple]:
        """Times this student is free on weekdays 9-5 (no class, no shift, nothing on the calendar)."""
        taken = [(b.start, b.end) for b in self.store.busy()] + [(s.start, s.end) for s in self.store.shifts()]
        out = []
        for d in range(5):
            day = monday + timedelta(days=d)
            for half in range(18, 34 - minutes // 30 + 1):
                st = at(day, half // 2, 30 * (half % 2))
                en = st + timedelta(minutes=minutes)
                if not any(overlaps(st, en, a, b) for a, b in taken):
                    out.append((st, en))
        return out

    async def ask_meeting(self, monday: date, minutes: int = 30) -> str:
        opts_all = self.store.get("meeting_opts", {})
        rid = f"meet-{self.me}-{len(opts_all) + 1}"
        req = MeetingRequest(request_id=rid, agent_id=self.me, minutes=minutes, slots=self.free_slots(monday, minutes))
        opts = MeetingOptions(**await self.to_steward("/meeting/request", req))
        if not opts.slots:
            return "Your manager has no time next week that matches yours. Text me again and I'll try the week after."
        opts_all[rid] = [[s.isoformat(), e.isoformat()] for s, e in opts.slots]
        self.store.put("meeting_opts", opts_all)
        await self.notify(explain.meeting_options(opts.slots),
                          [(fmt_span(s, e), f"book:{rid}:{i}") for i, (s, e) in enumerate(opts.slots)], kind="ask")
        return "I found times that work for you and your manager."

    async def book(self, rid: str, i: int) -> str:
        opts = self.store.get("meeting_opts", {}).get(rid)
        if not opts or i >= len(opts):
            return "That meeting is already booked or gone."
        s, e = (datetime.fromisoformat(x) for x in opts[i])
        await self.to_steward("/meeting/book", MeetingBook(request_id=rid, agent_id=self.me, start=s, end=e))
        self.store.add_busy([BusyBlock(id=f"meet-{rid}", start=s, end=e, kind="appointment",
                                       label="Meeting with your supervisor", source="calendar")])
        await self.schedule_changed()
        left = self.store.get("meeting_opts", {})
        left.pop(rid, None)
        self.store.put("meeting_opts", left)
        return f"Booked: {fmt_span(s, e)} with your supervisor. It's on your week now, and I'll keep shifts off it."

    async def invited(self, m: MeetingInvite) -> None:
        invites = self.store.get("invites", {})
        invites[m.meeting_id] = m.model_dump(mode="json")
        self.store.put("invites", invites)
        clash = next((b.label for b in self.store.busy() if overlaps(m.start, m.end, b.start, b.end)), None) or \
            next((f"your {s.label} shift" for s in self.store.shifts() if overlaps(m.start, m.end, s.start, s.end)), None)
        buttons = [("I'll be there", f"rsvp:yes:{m.meeting_id}"), ("Can't make it", f"rsvp:no:{m.meeting_id}")]
        await self.notify(explain.invite(m.title, fmt_span(m.start, m.end), clash),
                          buttons[::-1] if clash else buttons, kind="ask")

    async def rsvp(self, going: bool, mid: str) -> str:
        inv = self.store.get("invites", {}).get(mid)
        if not inv:
            return "That invite is gone."
        await self.to_steward("/meeting/rsvp", Rsvp(meeting_id=mid, agent_id=self.me, going=going))
        if going:
            self.store.add_busy([BusyBlock(id=f"team-{mid}", start=datetime.fromisoformat(inv["start"]),
                                           end=datetime.fromisoformat(inv["end"]), kind="other", label=inv["title"],
                                           source="calendar")])
            await self.schedule_changed()
            return "Added to your week. Your manager only sees that you're coming."
        return "OK, I told your manager you can't make it, with no reason."

    async def want_hours(self, monday: date) -> str:
        st = self.store.student()
        self.store.save_student(st.model_copy(update={"prefs": st.prefs.model_copy(update={"wants_more_hours": True})}))
        room = binding(st, self.store.shifts(), monday)
        left = f"${room.room:.0f} of Work-Study award" if room.unit == "$" else f"{room.room:g} h"
        return ("Got it. When your manager posts an extra shift, I'll offer to take it if it fits your classes and "
                f"every limit I check for you (your tightest limit leaves {left} this week). You confirm each one "
                "before it's yours.")

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
        for ref in sorted(req.items, key=lambda r: self.preference(r, give)):
            if ref.owner == self.me:
                continue
            a = self.availability(ref, giving=req.you_give)
            if a == "no" or not self.rule_ok([to_shift(ref)], drop):
                continue
            if a == "yes" and self.near_limit([to_shift(ref)], drop) and self.answer(ref.shift_id) != "yes":
                a = "unsure"  # inside the F-1 buffer: the student decides, not the mascot
            (yes if a == "yes" else unsure).append(ref)
        if yes:
            choice = yes[0]
            self.remember("picked", choice.shift_id)
            self.store.note(f"Round {req.iteration} ({req.phase}): picked {to_shift(choice).label}.")
            return Pick(round_id=req.round_id, iteration=req.iteration, agent_id=self.me, shift_id=choice.shift_id)
        if unsure:
            await self.ask(unsure[0], drop)
        else:
            self.store.note(f"Round {req.iteration} ({req.phase}): nothing fits, passed.")
        return Pick(round_id=req.round_id, iteration=req.iteration, agent_id=self.me, shift_id=None)

    def answer(self, shift_id: str) -> str | None:
        return self.store.get("answers", {}).get(shift_id)

    def preference(self, ref: ShiftRef, give: Shift | None) -> tuple:
        """The student's private ranking: shifts in the same part of the day as the one they give up first
        (it keeps their routine), then earlier in the week."""
        same_part = give is not None and (ref.start.hour >= 17) == (give.start.hour >= 17)
        return (0 if same_part else 1, ref.start)

    def near_limit(self, add: list[Shift], drop: list[Shift]) -> bool:
        st = self.store.student()
        if not st.limits.f1_or_j1 or not add:
            return False
        after = [s for s in self.store.shifts() if s.id not in {d.id for d in drop}] + add
        return near_f1_limit(st, after, week_start(add[0].start.date()))

    async def ask(self, ref: ShiftRef, drop: list[Shift] | None = None) -> None:
        asked = self.store.get("asked", [])
        if ref.shift_id in asked:
            return
        self.store.put("asked", asked + [ref.shift_id])
        st = self.store.student()
        label = to_shift(ref).label
        avoid = next((a for a in st.prefs.soft_avoid if a.weekday == ref.start.weekday()
                      and ref.start.hour < a.end_hour and a.start_hour < ref.end.hour), None)
        if avoid:
            self.store.note(f"Passed for now: {label} is open but it's your {avoid.label} slot. Asked you.")
            text, keep = explain.ask(label, avoid.label), "Keep my slot"
        else:
            monday = week_start(ref.start.date())
            after = [s for s in self.store.shifts() if s.id not in {d.id for d in drop or []}] + [to_shift(ref)]
            hours, cap = week_hours(st, after, monday), f1_cap_for(st, monday)
            self.store.note(f"Passed for now: {label} would put you at {hours:g} of {cap:g} on-campus hours. Asked you.")
            text, keep = explain.ask_limit(label, hours, cap, st.limits.other_employer_hours), "Leave room"
        buttons = [("Take it", f"ask:yes:{ref.shift_id}"), (keep, f"ask:no:{ref.shift_id}")]
        if keep == "Leave room":
            buttons.reverse()  # near a limit, the safe answer comes first
        await self.notify(text, buttons, kind="ask")

    # ---------- validation of the exact final ring ----------
    def my_moves(self, moves: list[Move]) -> tuple[list[Shift], list[Shift]]:
        adds = [to_shift(self.seen[m.shift_id]) for m in moves if m.to_agent == self.me and m.shift_id in self.seen]
        drops = [s for m in moves if m.from_agent == self.me and (s := self.store.shift(m.shift_id))]
        return adds, drops

    def remember(self, key: str, shift_id: str) -> None:
        self.store.put(key, sorted({*self.store.get(key, []), shift_id}))

    def asked_for(self, moves: list[Move]) -> bool:
        """A mascot only vouches for moves it asked for: shifts it picked, and shifts its student asked to trade.
        Anything else is a probe ("would one more 4-hour shift fit?") and gets the same plain no as a real no."""
        picked, requested = set(self.store.get("picked", [])), set(self.store.get("requested", []))
        return (all(m.shift_id in picked for m in moves if m.to_agent == self.me)
                and all(m.shift_id in requested for m in moves if m.from_agent == self.me))

    def ring_ok(self, moves: list[Move]) -> bool:
        if not self.asked_for(moves):
            self.store.note("A check came in for a trade I never asked for. Answered no; nothing about you left.")
            return False
        adds, drops = self.my_moves(moves)
        wanted = [m for m in moves if m.to_agent == self.me]
        if len(adds) != len(wanted):
            return False
        giving = drops[0].id if drops else None
        if any(self.availability(self.seen[s.id], giving=giving) != "yes" for s in adds):
            return False
        if self.near_limit(adds, drops) and any(self.answer(s.id) != "yes" for s in adds):
            return False
        return self.rule_ok(adds, drops)

    def check(self, rc: RingCheck) -> Eligibility:
        return Eligibility(ring_id=rc.ring_id, agent_id=self.me, ok=self.ring_ok(rc.moves))

    # ---------- two-phase commit ----------
    async def prepare(self, p: Prepare) -> Vote | None:
        if p.seen_version != self.store.version():
            return Vote(txn_id=p.txn_id, agent_id=self.me, vote="stale", ballot=p.ballot)
        if not self.ring_ok(p.moves):
            return Vote(txn_id=p.txn_id, agent_id=self.me, vote="no", ballot=p.ballot)
        self.store.put("hold", {"txn_id": p.txn_id, "ring_id": p.ring_id, "version": p.seen_version,
                                "moves": [m.model_dump() for m in p.moves], "ballot": p.ballot})
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
                self.remember("requested", parts[2])
                await self.send_trade(TradeRequest(agent_id=self.me, shift_id=parts[2]))
                self.store.note("You asked me to find a trade. Request sent: only the shift id left.")
                return ("On it. I'll look for a swap first, then a cover, in the next trade round. I'll text you "
                        "before anything moves; you don't need to do anything else.")
            return "OK, you keep the shift. Text me if that changes."
        if parts[0] == "out" and len(parts) == 2:
            return await self.tag_out(parts[1])
        if parts[0] == "issue" and len(parts) == 3:
            return await self.send_issue(parts[1], parts[2])
        if parts[0] == "book" and len(parts) == 3:
            return await self.book(parts[1], int(parts[2]))
        if parts[0] == "rsvp" and len(parts) == 3:
            return await self.rsvp(parts[1] == "yes", parts[2])
        if parts[0] == "ask" and len(parts) == 3:
            answers = self.store.get("answers", {})
            answers[parts[2]] = "yes" if parts[1] == "yes" else "no"
            self.store.put("answers", answers)
            self.store.note(f"You answered {answers[parts[2]]} about {parts[2]}.")
            return ("Got it. I'll offer to take it in the next round, and you'll still get a final Confirm before "
                    "anything moves." if parts[1] == "yes" else "OK, keeping your slot. I passed, and nobody is "
                    "told why.")
        if parts[0] in ("confirm", "decline") and len(parts) == 2:
            hold = self.store.get("hold")
            if not hold or hold["txn_id"] != parts[1]:
                return "That trade is no longer open."
            ballot = hold.get("ballot", "")
            if parts[0] == "decline":
                await self.send_vote(Vote(txn_id=parts[1], agent_id=self.me, vote="no", ballot=ballot))
                return "Declined. The trade is off, and nobody is told why."
            vote = "yes" if hold["version"] == self.store.version() else "stale"
            await self.send_vote(Vote(txn_id=parts[1], agent_id=self.me, vote=vote, ballot=ballot))
            return ("Confirmed. Waiting for the others and your manager; I'll text you the result." if vote == "yes"
                    else "Your week changed since this trade was set up, so I pulled out. Nothing moved.")
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
        monday = week_start((adds or drops)[0].start.date()) if adds or drops else None
        week = [s for s in self.store.shifts() if week_start(s.start.date()) == monday]
        await self.notify(explain.committed(adds, drops, week), kind="commit")

    async def schedule_changed(self) -> None:
        """Called after any edit to this student's week. A held trade with an old version must not commit."""
        self.store.bump()
        hold = self.store.get("hold")
        if hold and hold["version"] != self.store.version():
            await self.send_vote(Vote(txn_id=hold["txn_id"], agent_id=self.me, vote="stale",
                                      ballot=hold.get("ballot", "")))
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
            "shifts": [{"id": s.id, "label": s.label, "start": s.start.isoformat(), "end": s.end.isoformat()}
                       for s in shifts if week_start(s.start.date()) == monday],
            "busy": [{"label": b.label, "kind": b.kind, "source": b.source, "start": b.start.isoformat(),
                      "end": b.end.isoformat()} for b in self.store.busy()
                     if week_start(b.start.date()) == monday and b.kind != "class"],
            "classes": sorted({b.label for b in self.store.busy() if b.kind == "class"}),
            "rooms": [{"rule_id": r.rule_id, "used": r.used, "cap": r.cap, "room": r.room, "unit": r.unit}
                      for r in rooms(st, shifts, monday)],
            "runway": fws_runway(st, shifts, monday),
            "other_jobs": st.limits.other_employer_hours,
            "f1": bool(st.limits.f1_or_j1), "fws": bool(st.limits.fws),
            "wants_more_hours": bool(st.prefs.wants_more_hours),
            "collisions": self.store.get("collisions", []),
            "diary": self.store.diary(),
            "version": self.store.version(),
        }
